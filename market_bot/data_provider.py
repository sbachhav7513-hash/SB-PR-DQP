import requests
from datetime import datetime
from requests.adapters import HTTPAdapter
from typing import Dict, List, Optional
from urllib3.util.retry import Retry


class MarketDataProvider:
    QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
    CHART_URL_TEMPLATE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def __init__(self, max_retries: int = 3, backoff_factor: float = 1.0, timeout: int = 10) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json",
            }
        )

        retry = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def fetch_quote(self, symbol: str) -> Optional[Dict]:
        params = {"symbols": symbol}
        response = self.session.get(self.QUOTE_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        result = response.json().get("quoteResponse", {}).get("result", [])
        return result[0] if result else None

    def fetch_history(self, symbol: str, period: str = "1d", interval: str = "2m") -> List[Dict]:
        url = self.CHART_URL_TEMPLATE.format(symbol=symbol)
        params = {"range": period, "interval": interval, "includePrePost": "true"}
        response = self.session.get(url, params=params, timeout=self.timeout)
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
