"""Sentiment analysis agent — uses LLM to interpret news and gauge market sentiment."""

from __future__ import annotations

from src.agents.base_agent import BaseAgent, Signal
from src.data.news_data import NewsDataProvider


class SentimentAgent(BaseAgent):
    name = "sentiment"

    def __init__(self) -> None:
        super().__init__()
        self._news = NewsDataProvider()

    def analyze(self, symbol: str) -> Signal:
        articles = self._news.get_company_news(symbol, days_back=7)
        news_text = self._news.format_news_for_llm(articles)

        system_prompt = (
            "You are a senior sentiment analyst at a quantitative hedge fund. "
            "Your job is to analyze recent news articles about a company and determine "
            "the overall market sentiment and its likely impact on the stock price.\n\n"
            "Consider:\n"
            "- Tone and implications of headlines\n"
            "- Potential catalysts (earnings, product launches, regulatory)\n"
            "- Market narrative and momentum\n"
            "- Any red flags or positive surprises\n\n"
            "Respond ONLY with a JSON object:\n"
            '{"direction": "strong_buy|buy|hold|sell|strong_sell", '
            '"confidence": 0.0-1.0, "reasoning": "..."}'
        )

        user_prompt = (
            f"Analyze the sentiment for {symbol} based on these recent news articles:\n\n"
            f"{news_text}"
        )

        raw = self._call_llm(system_prompt, user_prompt)
        return self._parse_llm_signal(raw, symbol)
