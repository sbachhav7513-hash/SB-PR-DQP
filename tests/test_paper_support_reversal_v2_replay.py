from tools.paper_entry_replay import ReplayArm
from tools.paper_support_reversal_v2_replay import _best_baseline_trade_id


def _record(trade_id, net_r, *, status="complete"):
    return {
        "trade": {"trade_id": trade_id},
        "baseline": ReplayArm(status, net_r=net_r),
    }


def test_best_baseline_trade_is_selected_from_the_period_records():
    first_period = [
        _record("first-period-best", 0.8),
        _record("first-period-zero", 0.0),
        _record("missing", 10.0, status="missing_path"),
    ]
    second_period = [
        _record("second-period-best", 0.6),
        _record("second-period-other", -0.2),
    ]

    assert _best_baseline_trade_id(first_period) == "first-period-best"
    assert _best_baseline_trade_id(second_period) == "second-period-best"
    assert _best_baseline_trade_id([]) is None
