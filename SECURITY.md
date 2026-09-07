# Secret Handling

Credentials must be supplied through environment variables, not JSON files or source code.

## Telegram

PowerShell for the current terminal session:

```powershell
$env:TELEGRAM_BOT_TOKEN = "paste-token-here"
$env:TELEGRAM_CHAT_ID = "paste-chat-id-here"
python run_bot.py
```

The Yahoo bot ignores `telegram_token` and `telegram_chat_id` values in `config.json`.

## Kite

```powershell
$env:KITE_API_KEY = "paste-api-key-here"
$env:TELEGRAM_BOT_TOKEN = "paste-token-here"
$env:TELEGRAM_CHAT_ID = "paste-chat-id-here"
python run_kite_bot.py
```

The Kite authorizer keeps the daily access token in memory and does not write it to
`kite_config.json`. Set `KITE_ACCESS_TOKEN` yourself when starting with an existing token.

## Linux VPS authorization through an SSH tunnel

For a headless Linux VPS, configure the Kite app redirect URL as:

```text
http://127.0.0.1:8000/
```

From your local computer, open a tunnel and keep it running:

```bash
ssh -N -L 8000:127.0.0.1:8000 USER@VPS_IP
```

In a second SSH session on the VPS, start the bot:

```bash
cd /path/to/SB-PR-DQP
source venv/bin/activate
export KITE_API_KEY="your-api-key"
export TELEGRAM_BOT_TOKEN="your-telegram-token"
export TELEGRAM_CHAT_ID="your-chat-id"
python run_kite_bot.py
```

When the bot prints the Kite login URL, open it in your local browser. The SSH
tunnel forwards Kite's callback to the bot on the VPS. On a computer with a local
browser, use `python run_kite_bot.py --open-browser` instead.

## Required cleanup

1. Revoke and regenerate any token that was previously stored in `config.json`, pasted into chat, committed, or shared in logs. For Telegram, use BotFather; for Kite, revoke the active session in the broker dashboard.
2. Remove old credential values from local JSON files. Keep `config.json` and `kite_config.json` ignored and use the example files only as templates.
3. Never print environment variables, commit `.env` files, or put credentials in issue reports, screenshots, or README examples.
4. Before pushing, run `git diff --cached` and confirm no secret-looking values are staged.

Environment variables set with `$env:` last only for the current PowerShell process. A user-level
environment variable can be configured through Windows environment settings, but a dedicated secret
manager is preferable for production deployments.