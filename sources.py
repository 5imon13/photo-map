"""Fetch recent Taiwan news headlines about photo-worthy scenes and events."""
import html
import re
import time
from dataclasses import dataclass
from urllib.parse import quote

import feedparser

# Each query is one Google News search. "when:7d" limits results to the past week.
QUERIES = [
    "芒草",
    "楓紅 OR 賞楓",
    "落羽松",
    "花海 OR 盛開 OR 花季",
    "彼岸花 OR 石蒜 OR 波斯菊 OR 蕎麥花",
    "煙火",
    "遊行 OR 燈會 OR 祭典",
    "賞鳥 OR 稀有鳥",
    "雲海 OR 銀河 OR 流星雨",
]

FEED_URL = "https://news.google.com/rss/search?q={q}+when:7d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"


@dataclass
class Article:
    title: str
    source: str
    published: str
    link: str
    query: str


def _fetch_feed(url: str, attempts: int = 3):
    for attempt in range(attempts):
        try:
            return feedparser.parse(url)
        except OSError:  # connection reset / remote disconnected
            time.sleep(2 * (attempt + 1))
    return None


def fetch_articles(max_per_query: int = 25) -> list[Article]:
    seen: set[str] = set()
    articles: list[Article] = []
    for q in QUERIES:
        feed = _fetch_feed(FEED_URL.format(q=quote(q)))
        if feed is None:
            print(f"Skipped query after retries: {q}")
            continue
        for entry in feed.entries[:max_per_query]:
            # Google News titles look like "標題 - 來源媒體"
            title = html.unescape(re.sub(r"\s+-\s+[^-]+$", "", entry.title)).strip()
            if title in seen:
                continue
            seen.add(title)
            articles.append(Article(
                title=title,
                source=entry.get("source", {}).get("title", ""),
                published=entry.get("published", ""),
                link=entry.link,
                query=q,
            ))
    return articles


if __name__ == "__main__":
    for a in fetch_articles():
        print(f"[{a.query}] {a.title} ({a.source}, {a.published})")
