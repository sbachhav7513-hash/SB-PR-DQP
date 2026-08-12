import requests
from datetime import datetime
from typing import Dict, List, Optional


class MarketDataProvider:
    QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
    CHART_URL_TEMPLATE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def fetch_quote(self, symbol: str) -> Optional[Dict]:
        params = {"symbols": symbol}
        response = requests.get(self.QUOTE_URL, params=params, timeout=10)
        response.raise_for_status()
        result = response.json().get("quoteResponse", {}).get("result", [])
        return result[0] if result else None

    def fetch_history(self, symbol: str, period: str = "1d", interval: str = "2m") -> List[Dict]:
        url = self.CHART_URL_TEMPLATE.format(symbol=symbol)
        params = {"range": period, "interval": interval, "includePrePost": "true"}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json().get("chart", {}).get("result")
        if not payload:
            return []

        first = payload[0]
        timestamps = first.get("timestamp", [])
        quote = first.get("indicators", {}).get("quote", [])
        if not timestamps or not quote:
            return []

        closes = quote[0].get("close", [])
        output: List[Dict] = []
        for timestamp, close in zip(timestamps, closes):
            if close is None:
                continue
            output.append({"time": datetime.fromtimestamp(timestamp), "close": float(close)})
        return output
