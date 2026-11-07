from datetime import date, datetime
from zoneinfo import ZoneInfo

from tools import replay_exit_effects


IST = ZoneInfo("Asia/Kolkata")


def test_isolated_replay_reports_flag_effects_against_legacy_baseline(
    tmp_path, monkeypatch
):
    trade = {
        "trade_id": "trade-1",
        "contract_id": "NFO:NIFTY26N0924650CE",
        "_entry_time_parsed": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
    }
    monkeypatch.setattr(
        replay_exit_effects.replay,
        "load_trades",
        lambda root, start, end: [trade],
    )
    monkeypatch.setattr(
        replay_exit_effects.replay,
        "load_market_rows",
        lambda day_dir, contract, suffix: (
            [{"time": trade["_entry_time_parsed"], "open": 100, "high": 101, "low": 99, "close": 100}]
            if suffix == "candles"
            else [{"time": trade["_entry_time_parsed"], "bid": 99, "ask": 101}]
        ),
    )
    received = {}
    values = {
        "legacy_P1": 0.0,
        "runner_gap_v2_only": 10.0,
        "profit_lock_v2_only": 2.0,
        "trail_close_confirm_v2_only": 3.0,
        "profit_lock_plus_close_confirm": 5.0,
        "all_three_flags": 12.0,
    }

    def fake_simulate(trade, candles, quotes, args, policy, **settings):
        received[policy] = settings
        slippage_adjustment = args.slippage
        net = values[policy] - slippage_adjustment
        return replay_exit_effects.replay.Replay(
            policy,
            net,
            net,
            net,
            100.0,
            trade["_entry_time_parsed"],
            "test",
            0.0,
            True,
        )

    monkeypatch.setattr(
        replay_exit_effects.replay, "simulate_policy", fake_simulate
    )

    report = replay_exit_effects.build_report(
        tmp_path, date(2026, 11, 6), date(2026, 11, 6)
    )

    assert received["profit_lock_v2_only"] == {
        "runner_gap": 1.0,
        "profit_lock_r": 0.15,
    }
    assert received["trail_close_confirm_v2_only"] == {
        "runner_gap": 1.0,
        "close_confirm": True,
    }
    assert received["profit_lock_plus_close_confirm"] == {
        "runner_gap": 1.0,
        "profit_lock_r": 0.15,
        "close_confirm": True,
    }
    assert "| profit_lock_v2_only | flat_1_percent | 1 | 2.00 | 0.00 |" in report
    assert "| trail_close_confirm_v2_only | flat_1_percent | 1 | 3.00 | 0.00 |" in report
    assert "| profit_lock_plus_close_confirm | flat_1_percent | 1 | 5.00 | 0.00 |" in report
