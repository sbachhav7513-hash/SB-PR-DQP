import json

from paper_change_rollback_check import _net_pnl_rupees, run_check


def test_rollback_disables_only_underperforming_paper_change_at_threshold(tmp_path):
    config_path = tmp_path / "kite_config.json"
    trades_path = tmp_path / "trades.jsonl"
    decisions_path = tmp_path / "decision_log.jsonl"
    config_path.write_text(
        json.dumps(
            {
                "mode": "PAPER",
                "stale_quote_candle_fallback": True,
                "option_candle_momentum": True,
                "index_persistence_pass": True,
            }
        ),
        encoding="utf-8",
    )
    trades_path.write_text(
        "".join(
            json.dumps(
                {
                    "trade_id": f"added-{index}",
                    "paper_change_attributions": ["option_candle_momentum"],
                    "status": "closed",
                    "quantity": 65,
                    "pnl_rupees": -10,
                    "entry_fill_source": "best_ask",
                }
            )
            + "\n"
            for index in range(15)
        ),
        encoding="utf-8",
    )
    decisions_path.write_text(
        "".join(
            json.dumps(
                {
                    "timestamp": f"2026-10-{day:02d}T10:00:00+05:30",
                    "paper_change_flags": [
                        "stale_quote_candle_fallback",
                        "option_candle_momentum",
                        "index_persistence_pass",
                    ],
                }
            )
            + "\n"
            for day in range(14, 19)
        ),
        encoding="utf-8",
    )

    assert run_check(config_path, trades_path, decisions_path) == 0
    result = json.loads(config_path.read_text(encoding="utf-8"))
    assert result["option_candle_momentum"] is False
    assert result["stale_quote_candle_fallback"] is True
    assert result["index_persistence_pass"] is True


def test_removal_only_change_reports_candle_estimate_without_rollback(tmp_path, capsys):
    config_path = tmp_path / "kite_config.json"
    trades_path = tmp_path / "trades.jsonl"
    decisions_path = tmp_path / "decision_log.jsonl"
    candle_root = tmp_path / "candles"
    day_path = candle_root / "2026-10-30"
    day_path.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"mode": "PAPER", "premium_floor_v2": True}),
        encoding="utf-8",
    )
    trades_path.write_text("", encoding="utf-8")
    decisions_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-30T10:00:00+05:30",
                "signal_id": "removed-1",
                "ticker": "NIFTY_CE",
                "contract_id": "NFO:NIFTY26N0322950CE",
                "lot_size": 30,
                "signal": "BUY",
                "signal_ask": 100,
                "gate_measurements": {"ask": 100},
                "paper_change_gate_evaluations": {
                    "premium_floor_v2": {
                        "passed": False,
                        "would_pass_baseline": True,
                        "floor": 15,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (day_path / "candles.csv").write_text(
        "contract_id,timestamp,open,high,low,close,bid,ask\n"
        "NFO:NIFTY26N0322950CE,2026-10-30T10:01:00+05:30,95,101,89,92,91,93\n",
        encoding="utf-8",
    )

    assert run_check(config_path, trades_path, decisions_path, candle_root) == 0

    result = json.loads(config_path.read_text(encoding="utf-8"))
    assert result["premium_floor_v2"] is True
    output = capsys.readouterr().out
    assert "removed_signals=1 candle_estimates=1" in output
    assert "exit_reason=10pct_stop" in output
    assert "rollback=report_only" in output


def test_zerodha_costs_include_both_sides_slippage_and_order_fees():
    net = _net_pnl_rupees(
        {
            "status": "closed",
            "quantity": 10,
            "entry": 100,
            "exit_price": 110,
            "pnl_rupees": 100,
        }
    )

    assert net is not None
    assert net < 100 - 40 - 1


def test_banknifty_stop_rule_disables_flag_on_two_consecutive_losses(tmp_path):
    config_path = tmp_path / "kite_config.json"
    trades_path = tmp_path / "trades.jsonl"
    decisions_path = tmp_path / "decision_log.jsonl"
    config_path.write_text(
        json.dumps({"mode": "PAPER", "banknifty_caps_v2": True}),
        encoding="utf-8",
    )
    trades_path.write_text(
        "".join(
            json.dumps(
                {
                    "trade_id": f"bank-{index}",
                    "ticker": "BANKNIFTY_CE",
                    "paper_change_flags": ["banknifty_caps_v2"],
                    "status": "closed",
                    "quantity": 1,
                    "entry": 100,
                    "exit_price": 99,
                    "pnl_rupees": -1,
                    "timestamp": f"2026-10-30T10:0{index}:00+05:30",
                }
            )
            + "\n"
            for index in range(2)
        ),
        encoding="utf-8",
    )
    decisions_path.write_text("", encoding="utf-8")

    assert run_check(config_path, trades_path, decisions_path) == 0

    result = json.loads(config_path.read_text(encoding="utf-8"))
    assert result["banknifty_caps_v2"] is False


def test_banknifty_stop_rule_disables_flag_on_single_loss_over_2500(tmp_path):
    config_path = tmp_path / "kite_config.json"
    trades_path = tmp_path / "trades.jsonl"
    decisions_path = tmp_path / "decision_log.jsonl"
    config_path.write_text(
        json.dumps({"mode": "PAPER", "banknifty_caps_v2": True}),
        encoding="utf-8",
    )
    trades_path.write_text(
        json.dumps(
            {
                "trade_id": "bank-large-loss",
                "ticker": "BANKNIFTY_CE",
                "paper_change_flags": ["banknifty_caps_v2"],
                "status": "closed",
                "quantity": 30,
                "entry": 100,
                "exit_price": 0,
                "pnl_rupees": -3000,
                "timestamp": "2026-10-30T10:00:00+05:30",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decisions_path.write_text("", encoding="utf-8")

    assert run_check(config_path, trades_path, decisions_path) == 0

    result = json.loads(config_path.read_text(encoding="utf-8"))
    assert result["banknifty_caps_v2"] is False


def test_capital_based_risk_rolls_back_on_daily_loss_and_reports_investment(
    tmp_path, capsys
):
    config_path = tmp_path / "kite_config.json"
    trades_path = tmp_path / "trades.jsonl"
    decisions_path = tmp_path / "decision_log.jsonl"
    config_path.write_text(
        json.dumps({"mode": "PAPER", "capital_based_risk_v2": True}),
        encoding="utf-8",
    )
    trades_path.write_text(
        "".join(
            json.dumps(
                {
                    "trade_id": f"capital-{index}",
                    "ticker": "NIFTY_CE",
                    "paper_change_flags": ["capital_based_risk_v2"],
                    "paper_change_attributions": ["capital_based_risk_v2"],
                    "status": "closed",
                    "timestamp": f"2026-10-30T10:{index:02d}:00+05:30",
                    "quantity": 130,
                    "lots": 2,
                    "lot_size": 65,
                    "premium": 150,
                    "entry": 150,
                    "exit_price": 144,
                    "invested_amount": 19_500,
                    "risk_amount": 1_950,
                    "pnl_rupees": -900,
                }
            )
            + "\n"
            for index in range(7)
        ),
        encoding="utf-8",
    )
    decisions_path.write_text("", encoding="utf-8")

    assert run_check(config_path, trades_path, decisions_path) == 0

    result = json.loads(config_path.read_text(encoding="utf-8"))
    assert result["capital_based_risk_v2"] is False
    output = capsys.readouterr().out
    assert "daily realized loss INR 6000 reached" in output
    assert "trades=7" in output
    assert "invested_inr=136500.00" in output
    assert "risk_taken_inr=13650.00" in output
    assert "pnl_per_inr_invested=" in output


def test_capital_based_risk_rolls_back_on_single_trade_loss_over_risk_multiple(
    tmp_path,
):
    config_path = tmp_path / "kite_config.json"
    trades_path = tmp_path / "trades.jsonl"
    decisions_path = tmp_path / "decision_log.jsonl"
    config_path.write_text(
        json.dumps({"mode": "PAPER", "capital_based_risk_v2": True}),
        encoding="utf-8",
    )
    trades_path.write_text(
        json.dumps(
            {
                "trade_id": "capital-large-loss",
                "ticker": "NIFTY_CE",
                "paper_change_flags": ["capital_based_risk_v2"],
                "status": "closed",
                "timestamp": "2026-10-30T10:00:00+05:30",
                "quantity": 65,
                "lots": 1,
                "lot_size": 65,
                "entry": 100,
                "exit_price": 75,
                "risk_amount": 650,
                "pnl_rupees": -1000,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decisions_path.write_text("", encoding="utf-8")

    assert run_check(config_path, trades_path, decisions_path) == 0
    result = json.loads(config_path.read_text(encoding="utf-8"))
    assert result["capital_based_risk_v2"] is False


def test_capital_based_risk_rolls_back_when_daily_loss_limit_is_hit(tmp_path):
    config_path = tmp_path / "kite_config.json"
    trades_path = tmp_path / "trades.jsonl"
    decisions_path = tmp_path / "decision_log.jsonl"
    config_path.write_text(
        json.dumps({"mode": "PAPER", "capital_based_risk_v2": True}),
        encoding="utf-8",
    )
    trades_path.write_text(
        "".join(
            json.dumps(
                {
                    "trade_id": f"capital-daily-limit-{index}",
                    "ticker": "NIFTY_CE",
                    "paper_change_flags": ["capital_based_risk_v2"],
                    "status": "closed",
                    "timestamp": f"2026-10-30T10:{index:02d}:00+05:30",
                    "quantity": 1,
                    "entry": 100,
                    "exit_price": 100,
                    "risk_amount": 1000,
                    "pnl_rupees": -1000,
                }
            )
            + "\n"
            for index in range(10)
        ),
        encoding="utf-8",
    )
    decisions_path.write_text("", encoding="utf-8")

    assert run_check(config_path, trades_path, decisions_path) == 0
    result = json.loads(config_path.read_text(encoding="utf-8"))
    assert result["capital_based_risk_v2"] is False
