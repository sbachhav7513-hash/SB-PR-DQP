import sys
from pathlib import Path
from unittest.mock import Mock

import run_kite_bot


def test_authorize_only_refreshes_token_without_starting_bot(monkeypatch):
    authorize = Mock()
    bot = Mock()
    monkeypatch.setattr(run_kite_bot, "authorize", authorize)
    monkeypatch.setattr(run_kite_bot, "KiteTradingBot", bot)
    monkeypatch.setattr(
        sys, "argv", ["run_kite_bot.py", "--authorize-only"]
    )

    run_kite_bot.main()

    authorize.assert_called_once_with(
        Path("kite_config.json"), open_browser=False
    )
    bot.assert_not_called()


def test_authentication_modes_cannot_be_combined(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_kite_bot.py", "--no-auth", "--authorize-only"],
    )

    try:
        run_kite_bot.main()
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected conflicting auth modes to be rejected")


def test_sim_mode_skips_kite_token_preflight(monkeypatch):
    bot = Mock()
    has_valid_access_token = Mock(return_value=False)
    monkeypatch.setattr(run_kite_bot, "KiteTradingBot", bot)
    monkeypatch.setattr(
        run_kite_bot, "has_valid_access_token", has_valid_access_token
    )
    monkeypatch.setenv("BOT_SIM_MODE", "true")
    monkeypatch.setattr(sys, "argv", ["run_kite_bot.py", "--no-auth"])

    run_kite_bot.main()

    has_valid_access_token.assert_not_called()
    bot.assert_called_once_with("kite_config.json")
    bot.return_value.run.assert_called_once_with()
