"""Authorize with Kite Connect and start the trading bot."""

import argparse
import getpass
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from kiteconnect import KiteConnect

from market_bot.kite_main import KiteTradingBot
from market_bot.secrets import load_local_environment, set_local_environment


REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 8000

load_local_environment()


def has_valid_access_token(config_path: Path) -> bool:
    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    access_token = os.getenv("KITE_ACCESS_TOKEN")
    if not access_token or access_token.startswith("your_"):
        return False

    api_key = os.getenv("KITE_API_KEY")
    if not api_key:
        raise RuntimeError("Set KITE_API_KEY before starting Kite authorization.")
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    try:
        profile = kite.profile()
    except Exception as exc:
        print(f"Saved Kite access token is not valid: {exc}")
        return False

    print(
        "Saved Kite access token is valid for "
        f"{profile.get('user_id', 'your account')}. Skipping authentication."
    )
    return True


def authorize(config_path: Path, open_browser: bool = False) -> None:
    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    api_key = os.getenv("KITE_API_KEY")
    if not api_key:
        raise RuntimeError("Set KITE_API_KEY before starting Kite authorization.")
    kite = KiteConnect(api_key=api_key)
    api_secret = getpass.getpass("Kite API secret: ")
    result = {"access_token": None, "error": None}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query = parse_qs(urlparse(self.path).query)
            request_token = query.get("request_token", [None])[0]
            callback_error = query.get("error", [None])[0]
            callback_description = query.get("error_description", [None])[0]

            if callback_error:
                result["error"] = f"{callback_error}: {callback_description or 'no details'}"
                self._respond(400, "Kite authorization was rejected. Check the terminal.")
            elif not request_token:
                result["error"] = "No request_token was returned by Kite."
                self._respond(400, "No request token was returned by Kite.")
            else:
                try:
                    session = kite.generate_session(request_token, api_secret=api_secret)
                    result["access_token"] = session.get("access_token")
                    self._respond(200, "Authorization succeeded. You can close this window.")
                except Exception as exc:
                    result["error"] = f"{type(exc).__name__}: {exc}"
                    self._respond(500, "Kite token exchange failed. Check the terminal.")

            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def _respond(self, status: int, message: str) -> None:
            body = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    try:
        server = HTTPServer((REDIRECT_HOST, REDIRECT_PORT), CallbackHandler)
    except OSError as exc:
        raise RuntimeError(
            f"Cannot listen on {REDIRECT_HOST}:{REDIRECT_PORT}. "
            "Close another authorization process and try again."
        ) from exc

    login_url = kite.login_url()
    if open_browser:
        print("Complete Kite authorization in the browser window that opens.")
        webbrowser.open(login_url)
    else:
        print("Open this Kite login URL in your local browser:")
        print(login_url)
        print(
            "Keep the SSH tunnel to 127.0.0.1:8000 open so Kite can return to this process."
        )
    print("A fresh authorization is required because Kite access tokens expire daily.")
    try:
        server.serve_forever()
    finally:
        server.server_close()

    if result["error"]:
        raise RuntimeError(result["error"])
    if not result["access_token"]:
        raise RuntimeError("Kite returned no access token.")

    os.environ["KITE_ACCESS_TOKEN"] = result["access_token"]
    set_local_environment("KITE_ACCESS_TOKEN", result["access_token"])
    print("Fresh access token saved to .env. Starting the trading bot.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="kite_config.json", type=Path)
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the Kite login page locally instead of printing its URL.",
    )
    args = parser.parse_args()

    if not has_valid_access_token(args.config):
        authorize(args.config, open_browser=args.open_browser)
    KiteTradingBot(str(args.config)).run()


if __name__ == "__main__":
    main()
