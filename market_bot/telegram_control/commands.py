from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
HELP_TEXT = (
    "Commands:\n"
    "/help - show this list\n"
    "/status - bot state and open trades\n"
    "/pnl - today's realized/unrealized P&L\n"
    "/trades - today's closed trades\n"
    "/health - quote and feed health\n"
    "/pause - pause new entries; keep managing open trades\n"
    "/resume - resume new entries"
)


def _today(value: Any):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST).date()


def _open_journal_trades(bot) -> dict[str, dict]:
    trades = bot.trade_journal.read_trades()
    return {
        str(trade.get("ticker", trade.get("symbol", ""))): trade
        for trade in trades
        if trade.get("status") == "open"
    }


def _trade_id(trade: dict) -> str:
    value = trade.get("telegram_trade_id")
    return str(value) if value is not None else "?"


def _format_status(bot) -> str:
    now = datetime.now(IST)
    quote_times = getattr(bot, "_last_quote_timestamps", {})
    quote_ages = [
        max(0.0, (now - timestamp.astimezone(IST)).total_seconds())
        for timestamp in quote_times.values()
        if isinstance(timestamp, datetime)
    ]
    latest_age = min(quote_ages) if quote_ages else None
    age_text = f"{latest_age:.1f}s" if latest_age is not None else "unknown"
    paused = bool(getattr(bot, "_telegram_entries_paused", False))
    lines = [
        f"State: {'PAUSED' if paused else 'RUNNING'}",
        f"Mode: {getattr(bot, 'mode', 'PAPER')}",
        f"Config hash: {getattr(bot, 'config_hash', 'unknown')}",
        f"Last quote age: {age_text}",
    ]
    records = _open_journal_trades(bot)
    positions = getattr(bot.intraday_manager, "active_positions", {})
    if not positions:
        lines.append("Open trades: none")
        return "\n".join(lines)

    lines.append("Open trades:")
    for symbol, position in positions.items():
        record = records.get(symbol, {})
        ltp = getattr(bot, "latest_prices", {}).get(symbol)
        entry = float(position.get("entry_price", position.get("entry", 0.0)))
        quantity = int(position.get("quantity", 0))
        direction = str(position.get("direction", "UNKNOWN"))
        multiplier = bot.intraday_manager.contract_specs.get(symbol, {}).get(
            "multiplier",
            bot.intraday_manager.MULTIPLIERS.get(symbol, 1),
        )
        unrealized = (
            (float(ltp) - entry)
            * (1 if direction == "BUY" else -1)
            * quantity
            * float(multiplier)
            if ltp is not None
            else None
        )
        trailing = position.get("trailing_stop")
        trailing_state = (
            f"{'active' if position.get('trailing_active') else 'inactive'}"
            + (f" @ {float(trailing):.2f}" if trailing is not None else "")
        )
        manual_trigger = position.get("manual_exit_price")
        lines.append(
            f"#{_trade_id(record)} {symbol} {direction} qty={quantity} "
            f"entry={entry:.2f} LTP={float(ltp):.2f}" if ltp is not None
            else f"#{_trade_id(record)} {symbol} {direction} qty={quantity} "
            f"entry={entry:.2f} LTP=unknown"
        )
        lines.append(
            f"  unrealized P/L={unrealized:+.2f}" if unrealized is not None
            else "  unrealized P/L=unknown"
        )
        lines.append(
            f"  SL={float(position.get('stop_loss', 0.0)):.2f} "
            f"target={float(position.get('take_profit', 0.0)):.2f} "
            f"trailing={trailing_state} "
            f"manual trigger={manual_trigger if manual_trigger is not None else 'none'}"
        )
    return "\n".join(lines)


def _format_pnl(bot) -> str:
    today = datetime.now(IST).date()
    trades = bot.trade_journal.read_trades()
    closed_today = [
        trade for trade in trades
        if trade.get("status") == "closed"
        and _today(trade.get("closed_at")) == today
    ]
    realized = sum(float(trade.get("pnl_rupees", trade.get("pnl", 0.0))) for trade in closed_today)
    unrealized = 0.0
    for symbol, position in bot.intraday_manager.active_positions.items():
        ltp = getattr(bot, "latest_prices", {}).get(symbol)
        if ltp is None:
            continue
        entry = float(position.get("entry_price", position.get("entry", 0.0)))
        multiplier = bot.intraday_manager.contract_specs.get(symbol, {}).get(
            "multiplier",
            bot.intraday_manager.MULTIPLIERS.get(symbol, 1),
        )
        sign = 1 if position.get("direction") == "BUY" else -1
        unrealized += (
            (float(ltp) - entry)
            * sign
            * int(position.get("quantity", 0))
            * float(multiplier)
        )
    wins = sum(float(trade.get("pnl_rupees", trade.get("pnl", 0.0))) > 0 for trade in closed_today)
    losses = sum(float(trade.get("pnl_rupees", trade.get("pnl", 0.0))) < 0 for trade in closed_today)
    manager = bot.intraday_manager
    limit = float(getattr(manager, "daily_max_loss", 0.0))
    used = float(getattr(manager, "daily_realized_losses", 0.0))
    return (
        f"Today's realized P/L: {realized:+.2f}\n"
        f"Today's unrealized P/L: {unrealized:+.2f}\n"
        f"Today's closed trades: {len(closed_today)}; wins/losses: {wins}/{losses}\n"
        f"Daily loss used: {used:.2f} / {limit:.2f}"
    )


def _format_trades(bot) -> str:
    today = datetime.now(IST).date()
    trades = [
        trade for trade in bot.trade_journal.read_trades()
        if trade.get("status") == "closed"
        and _today(trade.get("closed_at")) == today
    ]
    if not trades:
        return "Today's closed trades: none"
    lines = ["Today's closed trades:"]
    for trade in trades:
        pnl = float(trade.get("pnl_rupees", trade.get("pnl", 0.0)))
        lines.append(
            f"#{_trade_id(trade)} {trade.get('ticker', trade.get('symbol', '?'))} "
            f"entry={float(trade.get('entry', 0.0)):.2f} "
            f"exit={float(trade.get('exit_price', 0.0)):.2f} "
            f"P/L={pnl:+.2f} reason={trade.get('reason', 'unknown')}"
        )
    return "\n".join(lines)


def _format_health(bot) -> str:
    now = datetime.now(IST)
    quote_times = getattr(bot, "_last_quote_timestamps", {})
    if not quote_times:
        quote_times = {
            symbol: quote.get("timestamp")
            for symbol, quote in getattr(bot, "option_quote_cache", {}).items()
            if quote.get("timestamp") is not None
        }
    underlying_times: dict[str, datetime] = {}
    for symbol, timestamp in quote_times.items():
        if not isinstance(timestamp, datetime):
            continue
        underlying = (
            symbol.rsplit("_", 1)[0]
            if symbol.endswith(("_CE", "_PE"))
            else symbol
        )
        previous = underlying_times.get(underlying)
        if previous is None or timestamp > previous:
            underlying_times[underlying] = timestamp
    stale = 0
    lines = ["Last quotes by underlying:"]
    for symbol, timestamp in sorted(underlying_times.items()):
        age = max(0.0, (now - timestamp.astimezone(IST)).total_seconds())
        stale += age > 60
        lines.append(f"{symbol}: {timestamp.astimezone(IST).isoformat()} ({age:.1f}s)")
    if not underlying_times:
        lines.append("none")
    stream = getattr(bot, "kite_stream", None)
    connected = bool(getattr(stream, "is_connected", False))
    tick_at = getattr(bot, "_last_loop_tick_at", None)
    tick_text = tick_at.astimezone(IST).isoformat() if isinstance(tick_at, datetime) else "unknown"
    lines.extend(
        [
            f"Stale quotes (>60s): {stale}",
            f"Feed/websocket: {'connected' if connected else 'disconnected'}",
            f"Last loop tick: {tick_text}",
        ]
    )
    return "\n".join(lines)


def process_telegram_command(bot, raw_text: str) -> str:
    parts = raw_text.strip().split()
    if not parts:
        return "Usage: /help"
    command = parts[0].split("@", 1)[0].lower()
    if len(parts) != 1:
        return f"Usage: {command}"
    if command == "/help":
        return HELP_TEXT
    if command == "/status":
        return _format_status(bot)
    if command == "/pnl":
        return _format_pnl(bot)
    if command == "/trades":
        return _format_trades(bot)
    if command == "/health":
        return _format_health(bot)
    if command == "/pause":
        bot._telegram_entries_paused = True
        count = len(bot.intraday_manager.active_positions)
        return f"New entries paused. Open trades: {count}. Open trades remain managed."
    if command == "/resume":
        bot._telegram_entries_paused = False
        return "New entries resumed."
    return "Unknown command. Use /help."
