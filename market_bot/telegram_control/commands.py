from __future__ import annotations

from datetime import datetime
import math
import time
from typing import Any
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
HELP_TEXT = (
    "Commands:\n"
    "/help - show this list\n"
    "/status - bot state and open trades\n"
    "/pnl - today's realized/unrealized P&L\n"
    "/trades - today's closed trades\n"
    "/health - quote and feed health\n"
    "/pause - pause new entries; keep managing open trades\n"
    "/resume - resume new entries\n"
    "/exit <id> - close a trade (LIVE requires confirmation)\n"
    "/exitat <id> <price> - close a long option at or above a price\n"
    "/cancel <id> - clear a manual exit trigger\n"
    "/sl <id> <price> [force] - change stop loss\n"
    "/be <id> - move stop loss to breakeven\n"
    "/target <id> <price> - change target\n"
    "/simopen <symbol> <CE|PE> <qty> <entry> [SL target] - open a synthetic trade\n"
    "/simprice <symbol> <price> - set the simulation quote"
)


def _today(value: Any):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST).date()


def _open_journal_trades(bot) -> dict[str, dict]:
    trades = bot.trade_journal.read_trades()
    return {
        str(trade.get("ticker", trade.get("symbol", ""))): trade
        for trade in trades
        if trade.get("status") == "open"
    }


def _trade_id(trade: dict) -> str:
    value = trade.get("telegram_trade_id")
    return str(value) if value is not None else "?"


def _trade_reply(trade_id: str, message: str) -> str:
    return f"Trade #{trade_id}: {message}"


def _format_status(bot) -> str:
    now = datetime.now(IST)
    quote_times = getattr(bot, "_last_quote_timestamps", {})
    quote_ages = [
        max(0.0, (now - timestamp.astimezone(IST)).total_seconds())
        for timestamp in quote_times.values()
        if isinstance(timestamp, datetime)
    ]
    latest_age = min(quote_ages) if quote_ages else None
    age_text = f"{latest_age:.1f}s" if latest_age is not None else "unknown"
    paused = bool(getattr(bot, "_telegram_entries_paused", False))
    lines = [
        f"State: {'PAUSED' if paused else 'RUNNING'}",
        f"Mode: {getattr(bot, 'mode', 'PAPER')}",
        f"Config hash: {getattr(bot, 'config_hash', 'unknown')}",
        f"Last quote age: {age_text}",
    ]
    records = _open_journal_trades(bot)
    positions = getattr(bot.intraday_manager, "active_positions", {})
    if not positions:
        lines.append("Open trades: none")
        return "\n".join(lines)

    lines.append("Open trades:")
    for symbol, position in positions.items():
        record = records.get(symbol, {})
        ltp = getattr(bot, "latest_prices", {}).get(symbol)
        entry = float(position.get("entry_price", position.get("entry", 0.0)))
        quantity = int(position.get("quantity", 0))
        direction = str(position.get("direction", "UNKNOWN"))
        multiplier = bot.intraday_manager.contract_specs.get(symbol, {}).get(
            "multiplier",
            bot.intraday_manager.MULTIPLIERS.get(symbol, 1),
        )
        unrealized = (
            (float(ltp) - entry)
            * (1 if direction == "BUY" else -1)
            * quantity
            * float(multiplier)
            if ltp is not None
            else None
        )
        trailing = position.get("trailing_stop")
        trailing_state = (
            f"{'active' if position.get('trailing_active') else 'inactive'}"
            + (f" @ {float(trailing):.2f}" if trailing is not None else "")
        )
        manual_trigger = position.get("manual_exit_price")
        lines.append(
            f"#{_trade_id(record)} {symbol} {direction} qty={quantity} "
            f"entry={entry:.2f} LTP={float(ltp):.2f}" if ltp is not None
            else f"#{_trade_id(record)} {symbol} {direction} qty={quantity} "
            f"entry={entry:.2f} LTP=unknown"
        )
        lines.append(
            f"  unrealized P/L={unrealized:+.2f}" if unrealized is not None
            else "  unrealized P/L=unknown"
        )
        lines.append(
            f"  SL={float(position.get('stop_loss', 0.0)):.2f} "
            f"target={float(position.get('take_profit', 0.0)):.2f} "
            f"trailing={trailing_state} "
            f"manual trigger={manual_trigger if manual_trigger is not None else 'none'}"
        )
    return "\n".join(lines)


def _format_pnl(bot) -> str:
    today = datetime.now(IST).date()
    trades = bot.trade_journal.read_trades()
    closed_today = [
        trade for trade in trades
        if trade.get("status") == "closed"
        and _today(trade.get("closed_at")) == today
    ]
    realized = sum(float(trade.get("pnl_rupees", trade.get("pnl", 0.0))) for trade in closed_today)
    unrealized = 0.0
    for symbol, position in bot.intraday_manager.active_positions.items():
        ltp = getattr(bot, "latest_prices", {}).get(symbol)
        if ltp is None:
            continue
        entry = float(position.get("entry_price", position.get("entry", 0.0)))
        multiplier = bot.intraday_manager.contract_specs.get(symbol, {}).get(
            "multiplier",
            bot.intraday_manager.MULTIPLIERS.get(symbol, 1),
        )
        sign = 1 if position.get("direction") == "BUY" else -1
        unrealized += (
            (float(ltp) - entry)
            * sign
            * int(position.get("quantity", 0))
            * float(multiplier)
        )
    wins = sum(float(trade.get("pnl_rupees", trade.get("pnl", 0.0))) > 0 for trade in closed_today)
    losses = sum(float(trade.get("pnl_rupees", trade.get("pnl", 0.0))) < 0 for trade in closed_today)
    manager = bot.intraday_manager
    limit = float(getattr(manager, "daily_max_loss", 0.0))
    used = float(getattr(manager, "daily_realized_losses", 0.0))
    return (
        f"Today's realized P/L: {realized:+.2f}\n"
        f"Today's unrealized P/L: {unrealized:+.2f}\n"
        f"Today's closed trades: {len(closed_today)}; wins/losses: {wins}/{losses}\n"
        f"Daily loss used: {used:.2f} / {limit:.2f}"
    )


def _format_trades(bot) -> str:
    today = datetime.now(IST).date()
    trades = [
        trade for trade in bot.trade_journal.read_trades()
        if trade.get("status") == "closed"
        and _today(trade.get("closed_at")) == today
    ]
    if not trades:
        return "Today's closed trades: none"
    lines = ["Today's closed trades:"]
    for trade in trades:
        pnl = float(trade.get("pnl_rupees", trade.get("pnl", 0.0)))
        lines.append(
            f"#{_trade_id(trade)} {trade.get('ticker', trade.get('symbol', '?'))} "
            f"entry={float(trade.get('entry', 0.0)):.2f} "
            f"exit={float(trade.get('exit_price', 0.0)):.2f} "
            f"P/L={pnl:+.2f} reason={trade.get('reason', 'unknown')}"
        )
    return "\n".join(lines)


def _format_health(bot) -> str:
    now = datetime.now(IST)
    quote_times = getattr(bot, "_last_quote_timestamps", {})
    if not quote_times:
        quote_times = {
            symbol: quote.get("timestamp")
            for symbol, quote in getattr(bot, "option_quote_cache", {}).items()
            if quote.get("timestamp") is not None
        }
    underlying_times: dict[str, datetime] = {}
    for symbol, timestamp in quote_times.items():
        if not isinstance(timestamp, datetime):
            continue
        underlying = (
            symbol.rsplit("_", 1)[0]
            if symbol.endswith(("_CE", "_PE"))
            else symbol
        )
        previous = underlying_times.get(underlying)
        if previous is None or timestamp > previous:
            underlying_times[underlying] = timestamp
    stale = 0
    lines = ["Last quotes by underlying:"]
    for symbol, timestamp in sorted(underlying_times.items()):
        age = max(0.0, (now - timestamp.astimezone(IST)).total_seconds())
        stale += age > 60
        lines.append(f"{symbol}: {timestamp.astimezone(IST).isoformat()} ({age:.1f}s)")
    if not underlying_times:
        lines.append("none")
    stream = getattr(bot, "kite_stream", None)
    connected = bool(getattr(stream, "is_connected", False))
    tick_at = getattr(bot, "_last_loop_tick_at", None)
    tick_text = tick_at.astimezone(IST).isoformat() if isinstance(tick_at, datetime) else "unknown"
    lines.extend(
        [
            f"Stale quotes (>60s): {stale}",
            f"Feed/websocket: {'connected' if connected else 'disconnected'}",
            f"Last loop tick: {tick_text}",
        ]
    )
    return "\n".join(lines)


def _find_open_trade(bot, trade_id: str) -> tuple[dict | None, dict | None]:
    trades = bot.trade_journal.read_trades()
    trade = next(
        (
            candidate
            for candidate in reversed(trades)
            if str(candidate.get("telegram_trade_id")) == trade_id
        ),
        None,
    )
    if trade is None:
        return None, None
    if trade.get("status") != "open":
        return None, None
    symbol = str(trade.get("ticker", trade.get("symbol", "")))
    position = getattr(bot.intraday_manager, "active_positions", {}).get(symbol)
    if not position:
        return None, None
    return trade, position


def _missing_trade_reply(bot, trade_id: str) -> str:
    for candidate in reversed(bot.trade_journal.read_trades()):
        if str(candidate.get("telegram_trade_id")) == trade_id:
            message = "already closed" if candidate.get("status") != "open" else "trade not found"
            return _trade_reply(trade_id, message)
    return _trade_reply(trade_id, "not found or already closed")


def _current_price(bot, symbol: str) -> float | None:
    value = getattr(bot, "latest_prices", {}).get(symbol)
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and price > 0 else None


def _is_live(bot) -> bool:
    return bool(
        getattr(bot, "live_orders_enabled", False)
        or getattr(bot, "mode", "PAPER") == "LIVE"
    )


def _manual_exit(bot, trade_id: str) -> str:
    trade, position = _find_open_trade(bot, trade_id)
    if trade is None or position is None:
        return _missing_trade_reply(bot, trade_id)
    if _is_live(bot) and not getattr(bot, "telegram_control_live_orders", False):
        return _trade_reply(
            trade_id,
            "LIVE Telegram order placement is disabled; set TELEGRAM_CONTROL_LIVE_ORDERS=true to enable it.",
        )
    price = _current_price(bot, str(trade.get("ticker", trade.get("symbol", ""))))
    if price is None:
        return _trade_reply(trade_id, "Current LTP is unavailable; no exit was placed.")
    bot._close_position(str(trade.get("ticker", trade.get("symbol", ""))), price, "MANUAL_EXIT")
    remaining = getattr(bot.intraday_manager, "active_positions", {}).get(
        str(trade.get("ticker", trade.get("symbol", "")))
    )
    if remaining:
        error = remaining.get("telegram_exit_error")
        if error:
            return _trade_reply(
                trade_id, f"Exit failed; trade remains open and flagged. Error: {error}"
            )
        return _trade_reply(trade_id, "Exit failed; trade remains open and flagged.")
    return _trade_reply(trade_id, "exit completed.")


def _modify_trade(bot, trade: dict, position: dict, field: str, value: float) -> None:
    symbol = str(trade.get("ticker", trade.get("symbol", "")))
    action = str(position.get("direction", trade.get("action", ""))).upper()
    if getattr(bot, "live_orders_enabled", False) and not bot._quote_validated_long_option(
        symbol, position
    ):
        protection_order_id = position.get("protection_order_id")
        if not protection_order_id:
            raise RuntimeError("The live protective stop is unavailable; no change was made.")
        if field == "stop_loss":
            bot.kite_stream.modify_protective_stop_order(
                symbol, action, str(protection_order_id), value
            )

    old_value = float(position[field])
    changed_at = datetime.now(IST).isoformat(timespec="seconds")
    history = list(trade.get("risk_modifications") or [])
    history.append(
        {
            "field": field,
            "old_value": old_value,
            "new_value": value,
            "time": changed_at,
            "source": "MANUAL",
        }
    )
    position[field] = value
    if not bot.trade_journal.update_open_trade(
        symbol,
        {field: value, "risk_modifications": history, "updated_at": changed_at},
        action,
    ):
        position[field] = old_value
        raise RuntimeError("Could not persist the trade modification.")


def _handle_trade_command(bot, command: str, args: list[str], chat_id: str | None) -> str:
    expected = {
        "/exit": (1, 1),
        "/exitat": (2, 2),
        "/cancel": (1, 1),
        "/sl": (2, 3),
        "/be": (1, 1),
        "/target": (2, 2),
    }
    minimum, maximum = expected[command]
    if not minimum <= len(args) <= maximum:
        return f"Usage: {command} <id>" if maximum == 1 else f"Usage: {command} <id> <price> [force]"
    trade_id = args[0]
    if not trade_id.isdecimal():
        return f"Usage: {command} <id>"
    trade, position = _find_open_trade(bot, trade_id)
    if trade is None or position is None:
        return _missing_trade_reply(bot, trade_id)

    if command == "/exit":
        if not _is_live(bot):
            return _manual_exit(bot, trade_id)
        pending = getattr(bot, "_telegram_pending_exit_confirmation", None)
        if pending:
            return _trade_reply(
                trade_id,
                f"An exit confirmation is already pending for trade #{pending['trade_id']}.",
            )
        bot._telegram_pending_exit_confirmation = {
            "trade_id": trade_id,
            "chat_id": str(chat_id or ""),
            "expires_at": time.monotonic() + 30.0,
        }
        return _trade_reply(
            trade_id,
            "Confirm LIVE exit within 30 seconds by replying YES. Reply CANCEL to abort.",
        )

    symbol = str(trade.get("ticker", trade.get("symbol", "")))
    direction = str(position.get("direction", trade.get("action", ""))).upper()

    if command == "/cancel":
        if position.get("manual_exit_price") is None:
            return _trade_reply(trade_id, "has no manual exit trigger.")
        old_trigger = position["manual_exit_price"]
        position["manual_exit_price"] = None
        if not bot.trade_journal.update_open_trade(
            symbol, {"manual_exit_price": None}, direction
        ):
            position["manual_exit_price"] = old_trigger
            raise RuntimeError("Could not persist cancellation of the manual exit trigger.")
        return _trade_reply(
            trade_id,
            f"manual exit trigger cleared (from {float(old_trigger):.2f} to none).",
        )

    if _is_live(bot) and not getattr(bot, "telegram_control_live_orders", False):
        return _trade_reply(
            trade_id,
            "LIVE Telegram order control is disabled; set TELEGRAM_CONTROL_LIVE_ORDERS=true to enable it.",
        )

    ltp = _current_price(bot, symbol)
    if ltp is None:
        return _trade_reply(trade_id, "Current LTP is unavailable; no change was made.")
    entry = float(position.get("entry_price", position.get("entry", trade.get("entry", 0.0))))

    if command == "/exitat":
        try:
            target = float(args[1])
        except ValueError:
            return _trade_reply(trade_id, "Usage: /exitat <id> <price>")
        if not math.isfinite(target) or target <= 0:
            return _trade_reply(trade_id, "Price must be a finite positive number.")
        if direction != "BUY" or not symbol.endswith(("_CE", "_PE")):
            return _trade_reply(trade_id, "/exitat is only available for long option positions.")
        if target <= ltp:
            return _trade_reply(
                trade_id, f"Price must be above current LTP ({ltp:.2f}); use /exit instead."
            )
        old_trigger = position.get("manual_exit_price")
        position["manual_exit_price"] = target
        if not bot.trade_journal.update_open_trade(
            symbol, {"manual_exit_price": target}, direction
        ):
            if old_trigger is None:
                position.pop("manual_exit_price", None)
            else:
                position["manual_exit_price"] = old_trigger
            return _trade_reply(trade_id, "Could not persist the manual exit trigger.")
        old_text = f"{float(old_trigger):.2f}" if old_trigger is not None else "none"
        return _trade_reply(
            trade_id, f"manual exit trigger set from {old_text} to {target:.2f}."
        )

    if command == "/be":
        if direction != "BUY" or ltp <= entry:
            return _trade_reply(
                trade_id, "Breakeven is available only when LTP is above entry."
            )
        target = entry
        field = "stop_loss"
    else:
        try:
            target = float(args[1])
        except ValueError:
            return _trade_reply(trade_id, f"Usage: {command} <id> <price> [force]")
        if not math.isfinite(target) or target <= 0:
            return _trade_reply(trade_id, "Price must be a finite positive number.")
        field = "stop_loss" if command == "/sl" else "take_profit"

    if command == "/sl":
        force = len(args) == 3 and args[2].lower() == "force"
        if len(args) == 3 and not force:
            return _trade_reply(trade_id, "Usage: /sl <id> <price> [force]")
        if (direction == "BUY" and target >= ltp) or (direction == "SELL" and target <= ltp):
            return _trade_reply(trade_id, "Stop loss must remain beyond the current market price.")
        old_stop = float(position.get("stop_loss", 0.0))
        loosens = target < old_stop if direction == "BUY" else target > old_stop
        if loosens and not force:
            return _trade_reply(trade_id, "Loosening the stop loss requires the force option.")

    if command == "/target":
        if (direction == "BUY" and target <= ltp) or (direction == "SELL" and target >= ltp):
            return _trade_reply(
                trade_id, "Target must be beyond the current LTP in the profitable direction."
            )

    old_value = float(position[field])
    _modify_trade(bot, trade, position, field, target)
    label = "Stop loss" if field == "stop_loss" else "Target"
    return _trade_reply(
        trade_id, f"{label.lower()} updated from {old_value:.2f} to {target:.2f}."
    )


def _handle_simulation_command(bot, command: str, args: list[str]) -> str:
    if not getattr(bot, "simulation_mode", False):
        return f"{command} is available only when BOT_SIM_MODE=true."

    if command == "/simprice":
        if len(args) != 2:
            return "Usage: /simprice <symbol> <price>"
        try:
            price = float(args[1])
        except (TypeError, ValueError, OverflowError):
            return "Price must be a finite positive number."
        if not math.isfinite(price) or price <= 0:
            return "Price must be a finite positive number."
        try:
            symbol = args[0].upper()
            bot._set_simulation_price(symbol, price)
        except (RuntimeError, ValueError) as exc:
            return str(exc)
        return f"Simulation price for {symbol} set to {price:.2f}."

    if len(args) not in {4, 6}:
        return "Usage: /simopen <symbol> <CE|PE> <qty> <entry> [SL target]"
    symbol, side = args[0].upper(), args[1].upper()
    if side not in {"CE", "PE"}:
        return "Side must be CE or PE."
    if symbol.endswith(("_CE", "_PE")):
        if not symbol.endswith(f"_{side}"):
            return "The symbol option suffix must match the selected side."
    else:
        symbol = f"{symbol}_{side}"
    if not args[2].isdecimal() or int(args[2]) <= 0:
        return "Quantity must be a positive whole number."
    try:
        entry = float(args[3])
        stop_loss = float(args[4]) if len(args) == 6 else None
        take_profit = float(args[5]) if len(args) == 6 else None
    except (TypeError, ValueError, OverflowError):
        return "Prices must be finite positive numbers."
    if (
        not math.isfinite(entry)
        or entry <= 0
        or (
            stop_loss is not None
            and (not math.isfinite(stop_loss) or stop_loss <= 0)
        )
        or (
            take_profit is not None
            and (not math.isfinite(take_profit) or take_profit <= 0)
        )
    ):
        return "Prices must be finite positive numbers."
    try:
        trade_id, symbol = bot._open_simulated_trade(
            symbol,
            side,
            int(args[2]),
            entry,
            stop_loss,
            take_profit,
        )
    except (RuntimeError, ValueError) as exc:
        return str(exc)
    position = bot.intraday_manager.active_positions[symbol]
    return (
        f"Opened synthetic PAPER trade #{trade_id}: BUY {symbol} "
        f"qty={int(args[2])} entry={entry:.2f} "
        f"SL={float(position['stop_loss']):.2f} "
        f"target={float(position['take_profit']):.2f}."
    )


def process_telegram_command(bot, raw_text: str, chat_id: str | None = None) -> str:
    parts = raw_text.strip().split()
    if not parts:
        return "Usage: /help"
    command = parts[0].split("@", 1)[0].lower()
    if command in {"/simopen", "/simprice"}:
        return _handle_simulation_command(bot, command, parts[1:])
    if command in {"/exit", "/exitat", "/cancel", "/sl", "/be", "/target"}:
        pending = getattr(bot, "_telegram_pending_exit_confirmation", None)
        if pending and command == "/exit" and time.monotonic() >= pending["expires_at"]:
            bot._telegram_pending_exit_confirmation = None
            pending = None
        return _handle_trade_command(bot, command, parts[1:], chat_id)
    if len(parts) != 1:
        return f"Usage: {command}"
    pending = getattr(bot, "_telegram_pending_exit_confirmation", None)
    if pending:
        if time.monotonic() >= pending["expires_at"]:
            bot._telegram_pending_exit_confirmation = None
            return "Exit confirmation expired; no order was placed."
        if str(chat_id or "") != pending["chat_id"]:
            return "No pending exit confirmation for this chat."
        if parts[0].upper() == "YES":
            bot._telegram_pending_exit_confirmation = None
            return _manual_exit(bot, pending["trade_id"])
        if parts[0].upper() == "CANCEL":
            bot._telegram_pending_exit_confirmation = None
            return "LIVE exit cancelled; no order was placed."
    if parts[0].upper() in {"YES", "CANCEL"}:
        return "No pending exit confirmation for this chat."
    if command == "/help":
        return HELP_TEXT
    if command == "/status":
        return _format_status(bot)
    if command == "/pnl":
        return _format_pnl(bot)
    if command == "/trades":
        return _format_trades(bot)
    if command == "/health":
        return _format_health(bot)
    if command == "/pause":
        bot._telegram_entries_paused = True
        count = len(bot.intraday_manager.active_positions)
        return f"New entries paused. Open trades: {count}. Open trades remain managed."
    if command == "/resume":
        bot._telegram_entries_paused = False
        return "New entries resumed."
    return "Unknown command. Use /help."
