import pytest

from market_bot.strategy_config import (
    normalize_strategy_config,
    resolve_execution_mode,
)


def test_legacy_paper_strategy_values_become_shared_without_mutating_input(caplog):
    config = {
        "min_entry_score": 70,
        "paper_min_entry_score": 60,
        "paper_rsi_buy_block_above": 80,
        "paper_trading_enabled": True,
    }

    normalized = normalize_strategy_config(config)

    assert normalized["min_entry_score"] == 60
    assert normalized["rsi_buy_block_above"] == 80
    assert "paper_min_entry_score" not in normalized
    assert config["min_entry_score"] == 70
    assert "using the former paper strategy value" in caplog.text


@pytest.mark.parametrize(
    ("config", "environment_mode", "expected"),
    [
        ({"mode": "PAPER"}, None, "PAPER"),
        ({"mode": "PAPER"}, "LIVE", "LIVE"),
        ({"paper_trading_enabled": False, "live_orders_enabled": True}, None, "LIVE"),
        ({}, None, "PAPER"),
    ],
)
def test_execution_mode_resolves_to_paper_or_live(
    config, environment_mode, expected
):
    assert resolve_execution_mode(config, environment_mode) == expected


@pytest.mark.parametrize(
    ("config", "environment_mode"),
    [
        ({"mode": "SIMULATION"}, None),
        ({"paper_trading_enabled": False, "live_orders_enabled": False}, None),
        ({"paper_trading_enabled": True, "live_orders_enabled": True}, None),
        ({"mode": "PAPER"}, ""),
    ],
)
def test_execution_mode_rejects_ambiguous_or_invalid_values(
    config, environment_mode
):
    with pytest.raises(ValueError):
        resolve_execution_mode(config, environment_mode)
