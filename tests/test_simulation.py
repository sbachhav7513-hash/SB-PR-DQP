import json
from datetime import datetime

import pytest

from market_bot.kite_main import KiteTradingBot
from market_bot.simulation import SimulationMarketStream
from market_bot.telegram_control.commands import process_telegram_command


def test_simulation_feed_replays_json_and_accepts_manual_override(tmp_path):
    feed_path = tmp_path / "prices.json"
    feed_path.write_text(
        json.dumps(
            {
                "ticks": [
                    {"symbol": "SIM_CE", "price": 10},
                    {"symbol": "SIM_CE", "price": 12},
                ]
            }
        ),
        encoding="utf-8",
    )
    received = []
    feed = SimulationMarketStream(
        {},
        on_tick_callback=received.append,
        script_path=feed_path,
    )

    assert feed.tick_interval_seconds == 2.0
    assert feed.advance()
    assert feed.advance()
    assert not feed.advance()
    assert [tick.last_price for tick in received] == [10.0, 12.0]
    assert all(tick.bid == tick.ask == tick.last_price for tick in received)
    assert all(isinstance(tick.timestamp, datetime) for tick in received)

    feed.set_price("SIM_CE", 15)
    assert received[-1].last_price == 15.0
    with pytest.raises(RuntimeError, match="disabled in simulation mode"):
        feed.place_market_order("SIM_CE", "BUY", 1)


def test_simulation_feed_reads_symbol_price_csv(tmp_path):
    feed_path = tmp_path / "prices.csv"
    feed_path.write_text(
        "symbol,price\nSIM_PE,20\nSIM_PE,18\n",
        encoding="utf-8",
    )
    received = []
    feed = SimulationMarketStream(
        {},
        on_tick_callback=received.append,
        script_path=feed_path,
    )

    assert feed.advance() and feed.advance()
    assert [tick.last_price for tick in received] == [20.0, 18.0]


@pytest.mark.parametrize(
    ("config_mode", "environment_mode"),
    [("LIVE", None), ("PAPER", "LIVE")],
)
def test_simulation_mode_refuses_live_before_broker_credentials(
    tmp_path, monkeypatch, config_mode, environment_mode
):
    config_path = tmp_path / "kite_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mode": config_mode,
                "trading_mode": "intraday_options",
                "instrument_tokens": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOT_SIM_MODE", "true")
    if environment_mode is None:
        monkeypatch.delenv("MODE", raising=False)
    else:
        monkeypatch.setenv("MODE", environment_mode)
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)

    with pytest.raises(ValueError, match="cannot be used when mode is LIVE"):
        KiteTradingBot(str(config_path))


def test_simulation_commands_are_disabled_outside_sim_mode():
    class NotSimulation:
        simulation_mode = False

    bot = NotSimulation()
    assert "only when BOT_SIM_MODE=true" in process_telegram_command(
        bot, "/simprice SIM_CE 10"
    )
    assert "only when BOT_SIM_MODE=true" in process_telegram_command(
        bot, "/simopen SIM CE 1 10"
    )
