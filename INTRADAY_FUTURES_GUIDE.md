# Intraday Futures Trading Setup Guide

## Overview

This bot has been upgraded to support **intraday futures trading** with automatic position management. This guide explains the key features and how to use them.

---

## Key Features for Intraday Trading

### 1. **Automatic Market Close Exit (3:15 PM)**
- All open positions are automatically closed at 3:15 PM (IST)
- Prevents overnight holding risk
- Forced exit ensures compliance with intraday rules
- Alert sent via Telegram when closing positions

### 2. **Smart Position Sizing**
```
Position Size = Account Risk / Risk Per Trade
- Account Risk = Account Size × Risk % per trade
- Risk Per Trade = (Entry Price - Stop Loss) × Multiplier × Quantity
```

**Example:**
```
Account: ₹100,000
Risk per trade: 1% = ₹1,000
NIFTY Entry: 19,200
Stop Loss: 19,100 (100 points)
Multiplier: ₹100 per point
Risk per 1 lot: 100 × ₹100 = ₹10,000

Quantity = ₹1,000 / ₹10,000 = 0.1 ≈ 1 contract minimum
```

### 3. **Tighter Stop Loss & Take Profit**
```
Long-term trading (Stocks):
- Stop Loss: -1.5%
- Take Profit: +3%

Intraday Futures (NEW):
- Stop Loss: -0.75%
- Take Profit: +1.5%

Why tighter:
- Market movements are faster
- Reduced overnight gap risk
- Better risk/reward in intraday timeframe
```

### 4. **Contract Symbols**
The bot now monitors these futures contracts:

| Contract | Symbol | Lot Size | Multiplier |
|----------|--------|----------|-----------|
| NIFTY 50 Index | NIFTY | 50 | ₹100/point |
| BANK NIFTY | BANKNIFTY | 15 | ₹100/point |
| TCS Stock Future | TCS | 1 | ₹1/point |
| INFY Stock Future | INFY | 1 | ₹1/point |
| WIPRO Stock Future | WIPRO | 1 | ₹1/point |

---

## Configuration Setup

### 1. Copy Example Config
```bash
cp kite_config.example.json kite_config.json
```

### 2. Update with Your Credentials
```json
{
  "kite_api_key": "your_api_key",
  "kite_access_token": "your_access_token",
  "trading_mode": "intraday_futures",
  "account_size": 100000,
  "risk_per_trade_pct": 1.0
}
```

### 3. Key Parameters

| Parameter | Default | Range | Notes |
|-----------|---------|-------|-------|
| `account_size` | 100,000 | 50,000-1,000,000 | Your trading capital |
| `risk_per_trade_pct` | 1.0% | 0.5%-2% | Risk per trade |
| `stop_loss_pct` | 0.75% | 0.5%-1.5% | Intraday stop loss |
| `take_profit_pct` | 1.5% | 1%-3% | Intraday take profit |
| `bar_interval_seconds` | 60 | 60-300 | 1 min = intraday |

---

## How It Works

### Trade Execution Flow

```
1. WebSocket receives real-time ticks
   ↓
2. Ticks aggregated into 1-minute candles
   ↓
3. Every candle: Check EMA crossover + RSI
   ↓
4. Signal found (BUY or SELL)?
   ↓
5. Calculate position size (smart sizing)
   ↓
6. Enter trade with SL & TP
   ↓
7. Monitor price:
   - Hit TP? → Auto close (profit)
   - Hit SL? → Auto close (loss)
   - 3:15 PM? → Force close (prevent overnight)
   ↓
8. Send Telegram alert
   ↓
9. Log trade to trades.jsonl
```

### Example Trade

```
NIFTY Entry Signal: BUY @ 19,200
- Account: ₹100,000
- Risk: 1% = ₹1,000
- SL: 19,100 (100 points = ₹10,000 risk per lot)
- TP: 19,406 (206 points = ₹20,600 profit per lot)

Position Size = ₹1,000 / ₹10,000 = 1 lot

Entry: 1 NIFTY lot @ 19,200
Stop Loss: 19,100
Take Profit: 19,406

Outcome 1: TP Hit @ 19,406
Profit: (19,406 - 19,200) × 50 × ₹100 = ₹1,030

Outcome 2: SL Hit @ 19,100
Loss: (19,100 - 19,200) × 50 × ₹100 = -₹500

Outcome 3: 3:15 PM reached
Force exit @ current price
```

---

## Running the Bot

### Prerequisites
1. Zerodha account with Kite Connect API enabled
2. API credentials (key & access token)
3. Telegram bot token & chat ID
4. Python 3.11+

### Step 1: Configure API Credentials
```bash
# Edit kite_config.json
vim kite_config.json

# Add your:
# - kite_api_key
# - kite_access_token
# - telegram_token
# - telegram_chat_id
```

### Step 2: Start the Bot
```bash
python run_kite_bot.py
```

### Output
```
[2024-01-15 09:16:45] INFO: Starting Kite Trading Bot - INTRADAY FUTURES MODE
[2024-01-15 09:16:45] INFO: Instruments: ['NIFTY', 'BANKNIFTY', 'TCS', 'INFY', 'WIPRO']
[2024-01-15 09:16:45] INFO: Bar interval: 60s
[2024-01-15 09:16:45] INFO: Market close exit time: 15:15:00
[2024-01-15 09:16:45] INFO: Risk per trade: 1.0%
[2024-01-15 09:16:45] INFO: Waiting for WebSocket connection...
[2024-01-15 09:16:47] INFO: WebSocket connected, streaming live data...
[2024-01-15 09:17:00] INFO: [NIFTY] Bar: O=19200.00 H=19210.00 L=19190.00 C=19205.00 V=1500
```

---

## Risk Management

### Position Sizing Formula
```
Quantity = (Account Size × Risk%) / (Risk Points × Multiplier)

Example:
- Account: ₹1,00,000
- Risk %: 1% = ₹1,000
- NIFTY price: 19,200
- SL: 19,100 (100 points)
- Multiplier: ₹100/point

Risk per contract = 100 × ₹100 = ₹10,000
Quantity = ₹1,000 / ₹10,000 = 0.1 → 1 lot minimum
```

### Risk Limits
- **Max risk per trade**: Calculated from `account_size × risk_per_trade_pct`
- **Max 1 contract**: Prevents over-leverage with small SL
- **Daily loss limit**: Monitor trades.jsonl and close bot if down 3%

### Safety Features
✅ Auto position sizing (no manual entry required)
✅ Forced market close exit (no overnight gaps)
✅ Telegram alerts for all trades
✅ Trade journal logging
✅ Stop loss enforcement

---

## Common Scenarios

### Scenario 1: Strong Buy Signal
```
- EMA crossover bullish
- RSI in zone (30-70)
- Score > 60
- Market hours (9:15 AM - 3:15 PM)

Action: ✅ Entry signal generated
- Calculate position size
- Enter with SL & TP
- Send Telegram alert
```

### Scenario 2: Approaching Market Close
```
- Time: 3:14 PM
- Open positions: 2
- Bot status: Checking for close time

Action: ✅ Next bar forces all exits
- Close NIFTY position
- Close BANKNIFTY position
- Send summary alert
```

### Scenario 3: Stop Loss Hit
```
- Entry: NIFTY @ 19,200
- Current: 19,100
- SL: 19,100

Action: ✅ Auto close
- Close 1 NIFTY lot
- Loss: ₹500
- Send alert: "STOP LOSS HIT"
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| No connection | API credentials invalid | Verify kite_api_key & access_token |
| Telegram alerts not sent | Token/Chat ID empty | Update telegram_token & telegram_chat_id |
| Positions not sized | Account size too small | Increase account_size or reduce risk_per_trade_pct |
| Too many trades | SL too wide | Reduce stop_loss_pct |
| Market close error | Time check failed | Ensure system time is correct (IST) |

---

## Cost Analysis

| Item | Cost |
|------|------|
| Zerodha Account | FREE |
| Kite API Access | FREE |
| WebSocket Data | FREE |
| Bot Running | FREE |
| **Per Trade** | 0.01-0.03% brokerage |

**Example:**
- NIFTY 1 lot @ 19,200 = ₹9,60,000 notional
- Brokerage (0.02%) = ~₹192 per trade
- P&L after 1 win: ₹1,030 - ₹192 = ₹838 net

---

## Best Practices

### ✅ DO:
- Start with smaller account size (₹50,000)
- Use 0.5-1% risk per trade
- Monitor bot during market hours
- Review trades.jsonl daily
- Adjust SL/TP based on market conditions

### ❌ DON'T:
- Use >2% risk per trade (overleveraged)
- Trade outside market hours (9:15 AM - 3:15 PM)
- Manually override positions (trust the bot)
- Trade more than 3 contracts simultaneously
- Ignore Telegram alerts

---

## Next Steps

1. **Test with Paper Trading**: Use Zerodha's paper trading first
2. **Start Small**: Trade NIFTY only, 1 lot per signal
3. **Monitor Closely**: First week, watch all trades live
4. **Optimize**: Adjust EMA periods & RSI thresholds
5. **Scale**: Increase capital only after consistent profits

---

## Support

For issues or questions:
1. Check trades.jsonl for historical trades
2. Review bot logs for error messages
3. Verify Kite API connectivity
4. Ensure Telegram bot is active
5. Check internet connection during trading hours

**Trading Hours:** 9:15 AM - 3:30 PM IST (Monday - Friday)
**Market Holidays:** NSE closure dates
