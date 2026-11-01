import json

from paper_change_rollback_check import run_check


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
