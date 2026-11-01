import pytest

from market_bot.strategy_config import (
    load_strategy_config,
    normalize_strategy_config,
    resolve_execution_mode,
    strategy_config_hash,
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


def test_paper_and_shared_adaptive_trail_gap_config_keys_are_equal():
    shared_config = normalize_strategy_config(
        {"option_adaptive_trail_gap_r": 1.0}
    )
    paper_config = normalize_strategy_config(
        {"paper_option_adaptive_trail_gap_r": 1.0}
    )

    assert (
        shared_config["option_adaptive_trail_gap_r"]
        == paper_config["option_adaptive_trail_gap_r"]
        == 1.0
    )


def test_shared_config_loader_normalizes_and_hash_excludes_credentials(tmp_path):
    config_path = tmp_path / "kite_config.json"
    config_path.write_text(
        '{"paper_min_entry_score": 65, "mode": "PAPER", '
        '"kite_api_key": "do-not-hash"}',
        encoding="utf-8",
    )

    loaded = load_strategy_config(config_path)
    canonical_hash = strategy_config_hash({"min_entry_score": 65})

    assert loaded["min_entry_score"] == 65
    assert "paper_min_entry_score" not in loaded
    assert strategy_config_hash(loaded) == canonical_hash
    assert strategy_config_hash(
        {"min_entry_score": 65, "kite_api_key": "different", "mode": "LIVE"}
    ) == canonical_hash


def test_shared_config_loader_rejects_non_object_json(tmp_path):
    config_path = tmp_path / "kite_config.json"
    config_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a JSON object"):
        load_strategy_config(config_path)


def test_capture_configuration_does_not_change_strategy_hash():
    baseline = strategy_config_hash({"option_min_premium": 12.0})

    assert strategy_config_hash(
        {"option_min_premium": 12.0, "capture_all_evaluated_contracts": True}
    ) == baseline
    assert strategy_config_hash(
        {"option_min_premium": 12.0, "capture_all_evaluated_contracts": False}
    ) == baseline


@pytest.mark.parametrize(
    "flag",
    [
        "stale_quote_candle_fallback",
        "option_candle_momentum",
        "index_persistence_pass",
        "premium_floor_v2",
        "banknifty_caps_v2",
        "nifty_vol_floor_v2",
        "capital_based_risk_v2",
    ],
)
def test_paper_recovery_flags_are_part_of_strategy_hash(flag):
    baseline = strategy_config_hash({})

    assert strategy_config_hash({flag: True}) != baseline
    assert strategy_config_hash({flag: False}) != baseline


def test_max_open_risk_setting_is_part_of_strategy_hash():
    assert strategy_config_hash({"max_open_risk_pct": 4.0}) != strategy_config_hash(
        {"max_open_risk_pct": 3.0}
    )


@pytest.mark.parametrize(
    "key",
    ["max_capital_per_trade_pct", "banknifty_max_capital_per_trade_pct"],
)
def test_capital_trade_limits_are_part_of_strategy_hash(key):
    assert strategy_config_hash({key: 20.0}) != strategy_config_hash(
        {key: 30.0}
    )


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
