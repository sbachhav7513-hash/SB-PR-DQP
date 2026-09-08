import json

from market_bot.config import BotConfig


def test_json_credentials_are_ignored(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "tickers": ["TEST"],
                "telegram_token": "token-in-file",
                "telegram_chat_id": "chat-in-file",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    config = BotConfig.load(str(config_path))

    assert config.telegram_token is None
    assert config.telegram_chat_id is None


def test_environment_credentials_are_used(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-from-environment")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat-from-environment")

    config = BotConfig.load(str(config_path))

    assert config.telegram_token == "token-from-environment"
    assert config.telegram_chat_id == "chat-from-environment"