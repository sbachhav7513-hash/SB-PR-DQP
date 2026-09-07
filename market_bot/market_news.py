from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests


logger = logging.getLogger(__name__)

DEFAULT_FEEDS = [
    "https://www.rbi.org.in/pressreleases_rss.xml",
    "https://www.federalreserve.gov/feeds/press_all.xml",
]
TRUSTED_FEED_HOSTS = frozenset({"www.rbi.org.in", "www.federalreserve.gov"})
HIGH_IMPACT_TERMS = (
    "rate hike", "rate cut", "interest rate", "inflation", "rbi", "fed",
    "war", "sanction", "default", "recession", "crash", "circuit breaker",
    "bank failure", "emergency", "earthquake", "terror", "oil surge",
)
POSITIVE_TERMS = ("rate cut", "stimulus", "growth", "jobs rise", "earnings beat")
NEGATIVE_TERMS = (
    "rate hike", "inflation", "war", "sanction", "default", "recession",
    "crash", "bank failure", "emergency", "oil surge",
)


@dataclass(frozen=True)
class NewsContext:
    fetched_at: Optional[str] = None
    risk_level: str = "UNKNOWN"
    sentiment: str = "NEUTRAL"
    headlines: List[str] = field(default_factory=list)
    sources: int = 0


def _published_at(value: str) -> Optional[datetime]:
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def fetch_news_context(feeds: List[str], timeout_seconds: float = 8.0) -> NewsContext:
    headlines: List[str] = []
    source_count = 0
    now = datetime.now(timezone.utc)
    for feed_url in feeds:
        parsed_feed = urlparse(feed_url)
        if parsed_feed.scheme != "https" or parsed_feed.hostname not in TRUSTED_FEED_HOSTS:
            logger.warning("Ignoring news feed outside trusted allowlist: %s", feed_url)
            continue
        try:
            response = requests.get(
                feed_url,
                timeout=timeout_seconds,
                headers={"User-Agent": "SB-PR-DQP market context reader/1.0"},
            )
            response.raise_for_status()
            redirected = urlparse(response.url)
            if redirected.scheme != "https" or redirected.hostname not in TRUSTED_FEED_HOSTS:
                logger.warning("Ignoring redirected news feed outside trusted allowlist: %s", response.url)
                continue
            root = ET.fromstring(response.content)
            source_count += 1
            for item in root.findall(".//item")[:10]:
                title = (item.findtext("title") or "").strip()
                published = _published_at(item.findtext("pubDate") or "")
                if title and (published is None or (now - published).total_seconds() <= 86400):
                    headlines.append(title)
        except (requests.RequestException, ET.ParseError, ValueError) as exc:
            logger.warning("News feed unavailable: %s", exc)

    unique_headlines = list(dict.fromkeys(headlines))[:20]
    text = " ".join(unique_headlines).lower()
    high_impact = sum(text.count(term) for term in HIGH_IMPACT_TERMS)
    negative = sum(text.count(term) for term in NEGATIVE_TERMS)
    positive = sum(text.count(term) for term in POSITIVE_TERMS)
    risk_level = "HIGH" if high_impact >= 2 else "ELEVATED" if high_impact else "NORMAL"
    sentiment = "NEGATIVE" if negative > positive else "POSITIVE" if positive > negative else "NEUTRAL"
    return NewsContext(
        fetched_at=now.isoformat(timespec="seconds"),
        risk_level=risk_level,
        sentiment=sentiment,
        headlines=unique_headlines,
        sources=source_count,
    )


class NewsMonitor:
    """Refresh market news in the background without blocking market ticks."""

    def __init__(self, feeds: Optional[List[str]] = None, refresh_seconds: int = 900) -> None:
        self.feeds = feeds or DEFAULT_FEEDS
        self.refresh_seconds = max(60, refresh_seconds)
        self._context = NewsContext()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="market-news", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> NewsContext:
        with self._lock:
            return self._context

    def _run(self) -> None:
        while not self._stop.is_set():
            context = fetch_news_context(self.feeds)
            with self._lock:
                self._context = context
            logger.info(
                "News context: risk=%s sentiment=%s headlines=%d sources=%d",
                context.risk_level, context.sentiment, len(context.headlines), context.sources,
            )
            self._stop.wait(self.refresh_seconds)


def apply_news_filter(signal: str, context: NewsContext) -> tuple[str, Optional[str]]:
    if signal in {"BUY", "SELL"} and context.risk_level == "HIGH":
        return "HOLD", "High-impact news risk; entry suppressed"
    return signal, None