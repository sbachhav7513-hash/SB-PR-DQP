from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent
AUTHORIZED_CHAT_ID = "101"


class ScenarioHarness:
    def __init__(self, bot, listener, sim_dir: Path) -> None:
        self.bot = bot
        self.listener = listener
        self.sim_dir = sim_dir
        self.replies: list[tuple[str, str]] = []
        self.update_id = 0

    def command(self, text: str, chat_id: str = AUTHORIZED_CHAT_ID) -> str | None:
        self.update_id += 1
        accepted = self.listener.handle_update(
            {
                "update_id": self.update_id,
                "message": {
                    "date": int(time.time()) + 1,
                    "chat": {"id": int(chat_id)},
                    "from": {"id": int(chat_id)},
                    "text": text,
                },
            }
        )
        if not accepted:
            return None
        self.bot._process_telegram_commands()
        reply_chat_id, reply = self.bot.telegram_reply_queue.get_nowait()
        if reply_chat_id != chat_id:
            raise AssertionError("Command reply was sent to the wrong chat")
        self.replies.append((text, reply))
        return reply

    def tick(self) -> bool:
        return self.bot.kite_stream.advance()

    def close(self) -> None:
        writer = getattr(self.bot, "option_capture_writer", None)
        if writer is not None:
            writer.close()


def _environment(values: dict[str, str | None]) -> dict[str, str | None]:
    previous = {key: os.environ.get(key) for key in values}
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    return previous


def _restore_environment(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _new_harness(
    name: str,
    ticks: list[float],
    run_dir: Path,
    config_path: Path,
    bot_factory: Callable,
    listener_factory: Callable,
) -> ScenarioHarness:
    sim_dir = run_dir / name
    sim_dir.mkdir(parents=True, exist_ok=True)
    feed_path = sim_dir / "prices.json"
    feed_path.write_text(
        json.dumps(
            {
                "ticks": [
                    {"symbol": "SIM_CE", "price": price} for price in ticks
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.environ["BOT_SIM_DIR"] = str(sim_dir)
    os.environ["BOT_SIM_FEED_FILE"] = str(feed_path)
    bot = bot_factory(str(config_path))
    listener = listener_factory(
        token="",
        allowed_chat_ids={AUTHORIZED_CHAT_ID},
        command_queue=bot.telegram_command_queue,
        reply_queue=bot.telegram_reply_queue,
    )
    return ScenarioHarness(bot, listener, sim_dir)


def _open(harness: ScenarioHarness) -> str:
    reply = harness.command("/simopen SIM CE 1 10 9 18")
    if reply is None or not reply.startswith("Opened synthetic PAPER trade #1"):
        raise AssertionError(f"Unexpected /simopen response: {reply!r}")
    return reply


def _rows(harness: ScenarioHarness) -> list[dict]:
    return harness.bot.trade_journal.read_trades()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _closed_trade(harness: ScenarioHarness) -> dict:
    closed = [trade for trade in _rows(harness) if trade["status"] == "closed"]
    _require(
        len(closed) == 1,
        f"Expected exactly one closed trade, got {len(closed)}",
    )
    return closed[0]


def _run_scenario(
    label: str,
    setup: Callable[[ScenarioHarness], None],
    harness: ScenarioHarness,
) -> tuple[bool, str]:
    outcome = "PASS"
    detail = ""
    try:
        setup(harness)
    except Exception as exc:
        outcome = "FAIL"
        detail = f"{type(exc).__name__}: {exc}"

    print(f"\n{label}: {outcome}" + (f" - {detail}" if detail else ""))
    print("Telegram replies:")
    if harness.replies:
        for command, reply in harness.replies:
            print(f"  {command} -> {reply}")
    else:
        print("  (none)")
    print("Journal rows:")
    print(json.dumps(_rows(harness), indent=2, default=str))
    print(f"Simulation files: {harness.sim_dir}")
    return outcome == "PASS", detail


def _case_a(harness: ScenarioHarness) -> None:
    harness.tick()
    _open(harness)
    reply = harness.command("/exitat 1 15")
    _require(reply is not None and "trigger set" in reply, "Manual target was not set")
    _require(harness.tick() and harness.tick(), "Scripted target ticks are missing")
    trade = _closed_trade(harness)
    _require(trade["exit_price"] >= 15, "Trade did not close at or above 15")
    _require(trade["exit_reason"] == "MANUAL_TARGET", "Wrong manual exit reason")
    _require(trade["exit_source"] == "MANUAL", "Wrong manual exit source")


def _case_b(harness: ScenarioHarness) -> None:
    harness.tick()
    _open(harness)
    reply = harness.command("/exitat 1 15")
    _require(reply is not None and "trigger set" in reply, "Manual target was not set")
    _require(harness.tick() and harness.tick(), "Scripted trailing ticks are missing")
    trade = _closed_trade(harness)
    _require(trade["reason"] == "TRAILING_STOP", "Trade did not exit on its trail")
    _require(trade["exit_source"] == "BOT", "Trailing stop has the wrong source")
    _require(trade["manual_exit_price"] is None, "Manual trigger was not cleared")


def _case_c(harness: ScenarioHarness) -> None:
    harness.tick()
    _open(harness)
    first = harness.command("/exit 1")
    second = harness.command("/exit 1")
    _require(first is not None and "exit completed" in first, "First exit failed")
    _require(second == "already closed", "Second exit did not report already closed")
    _require(
        len([row for row in _rows(harness) if row["status"] == "closed"]) == 1,
        "Repeated exit created more than one close",
    )


def _case_d(harness: ScenarioHarness) -> None:
    harness.tick()
    _open(harness)
    rejected_sl = harness.command("/sl 1 8")
    forced_sl = harness.command("/sl 1 8 force")
    rejected_be = harness.command("/be 1")
    price = harness.command("/simprice SIM_CE 11")
    accepted_be = harness.command("/be 1")
    _require(
        rejected_sl is not None and "requires the force" in rejected_sl,
        "Unforced stop-loss loosening was not rejected",
    )
    _require(forced_sl is not None and "updated" in forced_sl, "Forced SL failed")
    _require(
        rejected_be == "Breakeven is available only when LTP is above entry.",
        "Breakeven at or below entry was not rejected",
    )
    _require(price is not None and "set to 11.00" in price, "Manual quote failed")
    _require(accepted_be is not None and "updated" in accepted_be, "Breakeven failed")
    changes = _rows(harness)[0]["risk_modifications"]
    _require(
        any(
            change["source"] == "MANUAL"
            and change["field"] == "stop_loss"
            and change["old_value"] == 9.0
            and change["new_value"] == 8.0
            for change in changes
        ),
        "Forced SL change was not audited",
    )
    _require(
        any(
            change["source"] == "MANUAL" and change["field"] == "stop_loss"
            for change in changes
        ),
        "Breakeven change was not audited",
    )


def _case_e(harness: ScenarioHarness) -> None:
    harness.tick()
    _open(harness)
    pause = harness.command("/pause")
    no_entry = harness.command("/simopen OTHER CE 1 10 9 18")
    _require(pause is not None and "paused" in pause, "Pause command failed")
    _require(
        no_entry is not None and "paused" in no_entry,
        "Paused bot accepted a synthetic entry",
    )
    _require(harness.tick(), "Scripted stop-loss tick is missing")
    trade = _closed_trade(harness)
    _require(trade["reason"] == "STOP_LOSS", "Open trade stop-loss did not fire")
    _require(trade["exit_source"] == "BOT", "Stop-loss has the wrong source")


def _case_f(harness: ScenarioHarness) -> None:
    harness.tick()
    _open(harness)
    reply = harness.command("/exitat 1 10")
    _require(
        reply is not None and "use /exit instead" in reply,
        "Reached manual target was not rejected",
    )
    _require(_rows(harness)[0]["status"] == "open", "Rejected trigger closed trade")


def _case_g(harness: ScenarioHarness) -> None:
    _require(
        harness.command("/pause", chat_id="202") is None,
        "Unauthorized pause command was accepted",
    )
    _require(
        harness.command("/simopen SIM CE 1 10 9 18", chat_id="202") is None,
        "Unauthorized trade command was accepted",
    )
    _require(not harness.bot._telegram_entries_paused, "Unauthorized chat paused bot")
    _require(harness.bot.telegram_command_queue.empty(), "Unauthorized command queued")
    _require(harness.bot.telegram_reply_queue.empty(), "Unauthorized command got reply")
    _require(_rows(harness) == [], "Unauthorized command created a journal trade")


def _case_h(harness: ScenarioHarness) -> None:
    harness.tick()
    _open(harness)
    _require(
        "updated" in (harness.command("/sl 1 8 force") or ""),
        "Manual stop change failed",
    )
    _require(
        "updated" in (harness.command("/target 1 20") or ""),
        "Manual target change failed",
    )
    _require(
        "set to 11.00" in (harness.command("/simprice SIM_CE 11") or ""),
        "Manual quote failed",
    )
    _require(
        "updated" in (harness.command("/be 1") or ""),
        "Breakeven change failed",
    )
    _require(
        "exit completed" in (harness.command("/exit 1") or ""),
        "Manual exit failed",
    )
    trade = _closed_trade(harness)
    _require(trade["exit_source"] == "MANUAL", "Manual exit source was not journaled")
    _require(trade["exit_reason"] == "MANUAL_EXIT", "Manual exit reason was not journaled")
    manual_changes = [
        change
        for change in trade["risk_modifications"]
        if change["source"] == "MANUAL"
    ]
    _require(
        any(
            change["field"] == "stop_loss"
            and change["old_value"] == 9.0
            and change["new_value"] == 8.0
            for change in manual_changes
        ),
        "Stop-loss old/new values were not journaled",
    )
    _require(
        any(
            change["field"] == "take_profit"
            and change["old_value"] == 18.0
            and change["new_value"] == 20.0
            for change in manual_changes
        ),
        "Target old/new values were not journaled",
    )
    _require(
        all(
            "old_value" in change and "new_value" in change
            for change in manual_changes
        ),
        "A manual SL/target audit entry is missing old/new values",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Telegram-control scenarios against the simulation feed."
    )
    parser.add_argument(
        "--config",
        default=str(ROOT / "kite_config.example.json"),
        help="Bot configuration JSON (defaults to kite_config.example.json).",
    )
    parser.add_argument(
        "--sim-dir",
        default=None,
        help="Output directory (defaults to sim/scenarios/<timestamp>).",
    )
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    if not config_path.is_file():
        parser.error(f"Configuration file not found: {config_path}")
    run_dir = (
        Path(args.sim_dir).resolve()
        if args.sim_dir
        else ROOT
        / "sim"
        / "scenarios"
        / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    values = {
        "BOT_SIM_MODE": "true",
        "BOT_SIM_DIR": str(run_dir),
        "BOT_SIM_FEED_FILE": None,
        "BOT_SIM_TICK_INTERVAL_SECONDS": "0.01",
        "MODE": "PAPER",
        "TELEGRAM_BOT_TOKEN": None,
        "TELEGRAM_CHAT_ID": None,
        "TELEGRAM_TRADE_CHAT_ID": None,
        "TELEGRAM_ALLOWED_CHAT_IDS": None,
        "KITE_API_KEY": None,
        "KITE_ACCESS_TOKEN": None,
    }
    previous = _environment(values)
    try:
        logging.basicConfig(
            filename=str(run_dir / "kite_bot.log"),
            level=logging.WARNING,
            format="[%(asctime)s] %(levelname)s: %(message)s",
            force=True,
        )
        from market_bot.kite_main import KiteTradingBot
        from market_bot.telegram_control.listener import TelegramCommandListener

        cases = [
            ("a_manual_target", [10, 12, 15], _case_a),
            ("b_trailing_before_target", [10, 13, 12], _case_b),
            ("c_duplicate_exit", [10], _case_c),
            ("d_sl_and_be", [10], _case_d),
            ("e_pause_and_stop", [10, 8.9], _case_e),
            ("f_exitat_rejected", [10], _case_f),
            ("g_unauthorized", [10], _case_g),
            ("h_journal_audit", [10], _case_h),
        ]
        results = []
        for name, ticks, scenario in cases:
            harness = _new_harness(
                name,
                ticks,
                run_dir,
                config_path,
                KiteTradingBot,
                TelegramCommandListener,
            )
            try:
                results.append(
                    _run_scenario(name, scenario, harness)[0]
                )
            finally:
                harness.close()
        passed = sum(results)
        print(f"\nScenario summary: {passed}/{len(results)} PASS")
        return 0 if all(results) else 1
    finally:
        _restore_environment(previous)


if __name__ == "__main__":
    sys.exit(main())
