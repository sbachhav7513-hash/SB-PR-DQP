import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

import run_kite_bot


def test_authorize_shows_login_url_when_callback_port_is_occupied(
    tmp_path, monkeypatch, capsys
):
    config_path = tmp_path / "kite_config.json"
    config_path.write_text("{}", encoding="utf-8")
    login_url = "https://kite.example/login?api_key=test"

    kite = Mock()
    kite.login_url.return_value = login_url
    monkeypatch.setenv("KITE_API_KEY", "test")
    monkeypatch.setattr(run_kite_bot, "KiteConnect", Mock(return_value=kite))
    monkeypatch.setattr(
        run_kite_bot.getpass, "getpass", Mock(return_value="secret")
    )
    monkeypatch.setattr(
        run_kite_bot, "HTTPServer", Mock(side_effect=OSError("Address in use"))
    )

    with pytest.raises(RuntimeError, match="Cannot listen on 127.0.0.1:8000"):
        run_kite_bot.authorize(config_path)

    output = capsys.readouterr().out
    assert login_url in output
    assert (
        "authorization cannot complete until the callback port 8000 is free"
        in output
    )


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


def test_sim_mode_skips_kite_token_preflight(monkeypatch, tmp_path):
    bot = Mock()
    has_valid_access_token = Mock(return_value=False)
    monkeypatch.setattr(run_kite_bot, "KiteTradingBot", bot)
    monkeypatch.setattr(
        run_kite_bot, "has_valid_access_token", has_valid_access_token
    )
    monkeypatch.setenv("BOT_SIM_MODE", "true")
    monkeypatch.setenv("BOT_SIM_DIR", str(tmp_path / "simulation"))
    monkeypatch.setattr(sys, "argv", ["run_kite_bot.py", "--no-auth"])

    run_kite_bot.main()

    has_valid_access_token.assert_not_called()
    bot.assert_called_once_with("kite_config.json")
    bot.return_value.run.assert_called_once_with()
    assert (tmp_path / "simulation" / "kite_bot.log").is_file()
