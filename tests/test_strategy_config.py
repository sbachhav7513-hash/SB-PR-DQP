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
