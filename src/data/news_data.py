"""News / sentiment data provider using Finnhub (free tier) and web search."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from config.settings import get_settings


@dataclass(frozen=True)
class NewsArticle:
    headline: str
    summary: str
    source: str
    url: str
    published: datetime
    related_symbols: list[str]


class NewsDataProvider:
    """Fetch recent news articles for market analysis."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def get_company_news(
        self,
        symbol: str,
        days_back: int = 7,
    ) -> list[NewsArticle]:
        """Fetch recent news for *symbol* from Finnhub."""
        api_key = self._settings.finnhub_api_key
        if not api_key:
            return []

        end = datetime.now()
        start = end - timedelta(days=days_back)
        url = "https://finnhub.io/api/v1/company-news"
        params = {
            "symbol": symbol,
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
            "token": api_key,
        }

        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        articles: list[NewsArticle] = []
        for item in resp.json()[:20]:  # Limit to 20 articles
            articles.append(
                NewsArticle(
                    headline=item.get("headline", ""),
                    summary=item.get("summary", ""),
                    source=item.get("source", ""),
                    url=item.get("url", ""),
                    published=datetime.fromtimestamp(item.get("datetime", 0)),
                    related_symbols=item.get("related", "").split(",") if item.get("related") else [symbol],
                )
            )
        return articles

    def get_market_news(self, category: str = "general") -> list[NewsArticle]:
        """Fetch general market news from Finnhub."""
        api_key = self._settings.finnhub_api_key
        if not api_key:
            return []

        url = "https://finnhub.io/api/v1/news"
        params = {"category": category, "token": api_key}

        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        articles: list[NewsArticle] = []
        for item in resp.json()[:20]:
            articles.append(
                NewsArticle(
                    headline=item.get("headline", ""),
                    summary=item.get("summary", ""),
                    source=item.get("source", ""),
                    url=item.get("url", ""),
                    published=datetime.fromtimestamp(item.get("datetime", 0)),
                    related_symbols=[],
                )
            )
        return articles

    def format_news_for_llm(self, articles: list[NewsArticle]) -> str:
        """Format articles into a text block suitable for LLM consumption."""
        if not articles:
            return "No recent news articles available."

        lines: list[str] = []
        for i, article in enumerate(articles, 1):
            lines.append(f"[{i}] {article.headline}")
            if article.summary:
                lines.append(f"    {article.summary[:300]}")
            lines.append(f"    Source: {article.source} | {article.published:%Y-%m-%d}")
            lines.append("")
        return "\n".join(lines)
