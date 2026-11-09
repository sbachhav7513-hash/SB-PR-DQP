import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from market_bot import paper_exit_rollback
from paper_change_rollback_check import run_check


IST = ZoneInfo("Asia/Kolkata")


def _trade(trade_id, day, *, pnl=0.0, risk=1000.0, max_r=0.0, flags=None):
    return {
        "trade_id": trade_id,
        "status": "closed",
        "closed_at": datetime(2026, 11, day, 10, 0, tzinfo=IST).isoformat(),
        "paper_exit_flags_at_entry": flags or ["runner_gap_v2"],
        "pnl_rupees": pnl,
        "planned_risk_rupees": risk,
        "max_favorable_r": max_r,
    }


def _partial_trade(trade_id, day, *, pnl=100.0):
    return {
        **_trade(
            trade_id,
            day,
            pnl=pnl,
            risk=10_000.0,
            flags=["partial_profit_v2"],
        ),
        "partial_status": "executed",
        "partial_exit_done": True,
        "entry_quantity": 100,
        "quantity": 100,
        "lot_size": 50,
        "remaining_quantity": 0,
        "exit_legs": [
            {
                "leg_type": "partial",
                "quantity": 50,
                "remaining_quantity_after": 50,
                "gross_pnl_rupees": 250.0,
            },
            {
                "leg_type": "final",
                "quantity": 50,
                "gross_pnl_rupees": pnl - 250.0,
            },
        ],
    }


def test_runner_drawdown_rollback_requires_three_events_across_five_sessions():
    trades = [
        _trade(f"runner-{day}", day, pnl=1500, max_r=3.0)
        for day in (2, 3, 4)
    ] + [
        _trade("quiet-5", 5, pnl=0, flags=["unrelated"]),
        _trade("quiet-6", 6, pnl=0, flags=["unrelated"]),
    ]

    result = paper_exit_rollback.evaluate_paper_exit_rollbacks(trades, Path())

    assert result["runner_gap_v2"]["rollback_required"] is True
    assert "runner_drawdowns=3" in result["runner_gap_v2"]["checks"][0]
    assert "closed_trade_sessions=5/5" in result["runner_gap_v2"]["checks"][0]


def test_single_trade_risk_and_tagged_daily_loss_trigger_rollback():
    trades = [
        _trade("oversized", 3, pnl=-1600, risk=1000),
        _trade("day-loss-a", 4, pnl=-3000, risk=5000),
        _trade("day-loss-b", 4, pnl=-3000, risk=5000),
    ]

    result = paper_exit_rollback.evaluate_paper_exit_rollbacks(trades, Path())

    assert result["runner_gap_v2"]["rollback_required"] is True
    reasons = " ".join(result["runner_gap_v2"]["rollback_reasons"])
    assert "oversized" in reasons
    assert "INR 6000" in reasons


def test_old_rule_comparison_uses_strict_half_r_and_first_ten(monkeypatch):
    trades = [
        _trade(
            f"trade-{index}",
            1 + index,
            flags=["profit_lock_v2"],
        )
        for index in range(10)
    ]
    deltas = {f"trade-{index}": 0.51 for index in range(3)}
    deltas["trade-3"] = 0.5
    monkeypatch.setattr(
        paper_exit_rollback,
        "_counterfactual_delta_r",
        lambda trade, flag, candle_root: (deltas.get(trade["trade_id"], 0.0), None),
    )

    deltas["trade-3"] = 0.51
    partial_result = paper_exit_rollback.evaluate_paper_exit_rollbacks(trades[:4], Path())
    assert partial_result["profit_lock_v2"]["rollback_required"] is False
    assert any(
        "tagged=4/10" in check
        for check in partial_result["profit_lock_v2"]["checks"]
    )

    deltas["trade-3"] = 0.5
    result = paper_exit_rollback.evaluate_paper_exit_rollbacks(trades, Path())
    assert result["profit_lock_v2"]["rollback_required"] is False
    assert any(
        "first_ten_old_rule_better=3 paired=10/10 missing=0" in check
        for check in result["profit_lock_v2"]["checks"]
    )

    deltas["trade-3"] = 0.51
    result = paper_exit_rollback.evaluate_paper_exit_rollbacks(trades, Path())
    assert result["profit_lock_v2"]["rollback_required"] is True
    assert "4 of the first ten tagged trades" in (
        result["profit_lock_v2"]["rollback_reasons"][0]
    )


def test_close_confirmation_counterfactual_uses_its_own_tagged_cohort(monkeypatch):
    trades = [
        _trade(
            f"trade-{index}",
            1 + index,
            flags=["trail_close_confirm_v2"],
        )
        for index in range(10)
    ]
    monkeypatch.setattr(
        paper_exit_rollback,
        "_counterfactual_delta_r",
        lambda trade, flag, candle_root: (
            0.75 if int(trade["trade_id"].split("-")[1]) < 4 else 0.0,
            None,
        ),
    )

    result = paper_exit_rollback.evaluate_paper_exit_rollbacks(trades, Path())

    assert result["trail_close_confirm_v2"]["rollback_required"] is True
    assert "old rule would have exited more than 0.5R better" in (
        result["trail_close_confirm_v2"]["rollback_reasons"][0]
    )


def test_partial_rollback_checks_whole_lot_accounting_and_leg_pnl():
    valid = _partial_trade("partial-valid", 1, pnl=100.0)
    invalid = _partial_trade("partial-invalid", 2, pnl=100.0)
    invalid["exit_legs"].append(dict(invalid["exit_legs"][0]))
    invalid["exit_legs"][0]["remaining_quantity_after"] = 25
    invalid["exit_legs"][1]["gross_pnl_rupees"] = 500.0

    result = paper_exit_rollback.evaluate_paper_exit_rollbacks(
        [valid, invalid], Path()
    )["partial_profit_v2"]

    assert result["rollback_required"] is True
    reason = " ".join(result["rollback_reasons"])
    assert "partial accounting validation failed" in reason
    assert "duplicate partial legs" in reason
    assert any("accounting_errors=" in check for check in result["checks"])


def test_partial_rollback_checks_daily_loss_for_tagged_partial_trades():
    trades = [
        _partial_trade("partial-loss-a", 4, pnl=-3000.0),
        _partial_trade("partial-loss-b", 4, pnl=-3000.0),
    ]

    result = paper_exit_rollback.evaluate_paper_exit_rollbacks(
        trades, Path()
    )["partial_profit_v2"]

    assert result["rollback_required"] is True
    assert "tagged partial-trade daily loss reached INR 6000.00" in (
        result["rollback_reasons"][0]
    )


def test_partial_rollback_paired_comparison_waits_for_ten_trades(monkeypatch):
    trades = [_partial_trade(f"partial-{index}", index + 1) for index in range(10)]
    calls = []

    def compare(trade, candle_root):
        calls.append(trade["trade_id"])
        return (0.75 if trade["trade_id"] in {
            "partial-0", "partial-1", "partial-2", "partial-3"
        } else 0.0), None

    monkeypatch.setattr(
        paper_exit_rollback, "_partial_counterfactual_delta_r", compare
    )
    early = paper_exit_rollback.evaluate_paper_exit_rollbacks(
        trades[:9], Path()
    )["partial_profit_v2"]
    assert calls == []
    assert any("eligible=9/10" in check for check in early["checks"])

    complete = paper_exit_rollback.evaluate_paper_exit_rollbacks(
        trades, Path()
    )["partial_profit_v2"]
    assert calls == [f"partial-{index}" for index in range(10)]
    assert complete["rollback_required"] is True
    assert "4 of the first ten eligible trades" in (
        complete["rollback_reasons"][0]
    )


def test_rollback_cli_disables_only_triggered_flag_and_prints_restart_steps(
    tmp_path, capsys
):
    config_path = tmp_path / "kite_config.json"
    trades_path = tmp_path / "trades.jsonl"
    decisions_path = tmp_path / "decision_log.jsonl"
    config_path.write_text(
        json.dumps(
            {
                "mode": "PAPER",
                "runner_gap_v2": True,
                "profit_lock_v2": True,
                "trail_close_confirm_v2": True,
            }
        ),
        encoding="utf-8",
    )
    trades_path.write_text(
        json.dumps(
            {
                **_trade("oversized", 3, pnl=-1600, risk=1000),
                "paper_exit_flags_at_entry": ["runner_gap_v2"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decisions_path.write_text("", encoding="utf-8")

    assert (
        run_check(
            config_path,
            trades_path,
            decisions_path,
            tmp_path / "option_candles",
        )
        == 0
    )

    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["runner_gap_v2"] is False
    assert config["profit_lock_v2"] is True
    assert config["trail_close_confirm_v2"] is True
    output = capsys.readouterr().out
    assert "Rollback switched OFF: runner_gap_v2" in output
    assert "stop and restart the PAPER bot" in output


def test_rollback_cli_disables_partial_flag_on_accounting_failure(tmp_path, capsys):
    config_path = tmp_path / "kite_config.json"
    trades_path = tmp_path / "trades.jsonl"
    decisions_path = tmp_path / "decision_log.jsonl"
    config_path.write_text(
        json.dumps(
            {
                "mode": "PAPER",
                "runner_gap_v2": True,
                "profit_lock_v2": True,
                "trail_close_confirm_v2": True,
                "partial_profit_v2": True,
            }
        ),
        encoding="utf-8",
    )
    invalid = _partial_trade("partial-invalid", 3)
    invalid["exit_legs"][0]["remaining_quantity_after"] = 0
    trades_path.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
    decisions_path.write_text("", encoding="utf-8")

    assert (
        run_check(
            config_path,
            trades_path,
            decisions_path,
            tmp_path / "option_candles",
        )
        == 0
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["partial_profit_v2"] is False
    assert config["runner_gap_v2"] is True
    assert config["profit_lock_v2"] is True
    assert config["trail_close_confirm_v2"] is True
    output = capsys.readouterr().out
    assert "Rollback switched OFF: partial_profit_v2" in output
    assert "tagged_trades=1" in output
