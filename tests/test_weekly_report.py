import json
from datetime import datetime

from market_bot.weekly_report import build_weekly_report, write_weekly_report


def test_weekly_report_selects_best_repeated_profile(tmp_path):
    timestamp = datetime.now().isoformat(timespec="seconds")
    trades = [
        {"timestamp": timestamp, "ticker": "GOOD", "action": "BUY", "status": "closed", "pnl": 10},
        {"timestamp": timestamp, "ticker": "GOOD", "action": "BUY", "status": "closed", "pnl": 20},
        {"timestamp": timestamp, "ticker": "BAD", "action": "SELL", "status": "closed", "pnl": -5},
        {"timestamp": timestamp, "ticker": "BAD", "action": "SELL", "status": "closed", "pnl": -1},
    ]
    decisions = [
        {"timestamp": timestamp, "signal": "BUY", "outcome": "trade_opened"},
        {"timestamp": timestamp, "signal": "HOLD", "outcome": "hold"},
    ]
    (tmp_path / "trades.jsonl").write_text(
        "\n".join(json.dumps(item) for item in trades) + "\n", encoding="utf-8"
    )
    (tmp_path / "decision_log.jsonl").write_text(
        "\n".join(json.dumps(item) for item in decisions) + "\n", encoding="utf-8"
    )

    report = build_weekly_report(str(tmp_path))
    output = write_weekly_report(str(tmp_path), output_dir=str(tmp_path))

    assert report["decisions_recorded"] == 2
    assert report["best_observed_profiles"][0]["profile"] == "GOOD:BUY"
    assert report["winning_trades"] == 2
    assert report["losing_trades"] == 2
    assert report["average_win"] == 15
    assert report["average_loss"] == -3
    assert report["profit_factor"] == 5
    assert report["performance_by_symbol"]["GOOD"]["total_pnl"] == 30
    assert report["performance_by_hour"][str(datetime.now().hour)]["trades"] == 4
    assert report["outcome_counts"]["trade_opened"] == 1
    assert output.exists()