from market_bot.backtest import run_backtest
from market_bot.engine import TradingScore


def candle(open_price, high, low, close, index):
    return {
        "time": index,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def test_backtest_enters_on_next_open_and_takes_target():
    history = [
        candle(100, 101, 99, 100, 0),
        candle(110, 112, 109, 111, 1),
        candle(111, 113, 110, 112, 2),
    ]

    def buy_signal(ticker, previous_candles):
        action = "BUY" if len(previous_candles) == 1 else "HOLD"
        return TradingScore(ticker, 90, action)

    result = run_backtest(
        "TEST",
        history,
        stop_loss_pct=1,
        take_profit_pct=1,
        signal_fn=buy_signal,
    )

    assert len(result.trades) == 1
    assert result.trades[0].entry_price == 110
    assert result.trades[0].exit_price == 111.1
    assert result.trades[0].exit_reason == "TAKE_PROFIT"


def test_backtest_uses_stop_when_stop_and_target_hit_same_bar():
    history = [
        candle(100, 100, 100, 100, 0),
        candle(100, 102, 98, 100, 1),
    ]

    result = run_backtest(
        "TEST",
        history,
        stop_loss_pct=1,
        take_profit_pct=1,
        signal_fn=lambda ticker, previous: TradingScore(ticker, 90, "BUY"),
    )

    assert result.trades[0].exit_reason == "STOP_LOSS"
    assert result.trades[0].return_pct == -1


def test_backtest_skips_malformed_candles():
    result = run_backtest("TEST", [{"close": 100}, {"open": "bad"}])

    assert result.trades == []