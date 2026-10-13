"""Fetch recent items about photo-worthy scenes and events in Taiwan from several sources.

Each source is independent: if one fails (site down, layout changed), it is skipped and
reported in the status, and the others still run.
"""
import html
import io
import json
import re
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import feedparser
from bs4 import BeautifulSoup

TAIWAN = timezone(timedelta(hours=8))
RECENT_DAYS = 30          # official announcements older than this are ignored
EVENT_LOOKAHEAD_DAYS = 30  # tourism events starting within this window
PTT_DAYS = 14
USER_AGENT = "Mozilla/5.0 (photo-map; personal project)"

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
GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q={q}+when:7d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

TOURISM_EVENTS_URL = "https://media.taiwan.net.tw/XMLReleaseAll_public/v2.0/Zh_tw/Event-json.zip"
TAIPEI_FLOWERS_URL = "https://flowersfestival.taipei/api/article.html"
NATIONAL_PARKS = {
    "陽明山國家公園": "www.ymsnp.gov.tw",
    "太魯閣國家公園": "www.taroko.gov.tw",
    "雪霸國家公園": "www.spnp.gov.tw",
    "台江國家公園": "www.tjnp.gov.tw",
}
FOREST_NEWS_URL = "https://recreation.forest.gov.tw/News/QueryNews?page={page}"

# PTT boards to read (latest posts). Board search is useless here: it returns all years, oldest hits included.
PTT_BOARDS = ["Hiking"]
PTT_SKIP_TITLES = re.compile(r"^(Re:|Fw:|\[(問題|徵|揪人|交易|贈送|公告|請益)\])")
PTT_MAX_PAGES = 6
# 觀光署 events that are rarely photo subjects (indoor, retail, admin); long-running programs are also skipped.
EVENT_SKIP_TITLES = re.compile(r"展覽|特展|聯展|個展|講座|課程|市集|集點|徵件|招募|比賽|研習|說明會|APP|線上")
EVENT_MAX_DAYS = 45


@dataclass
class Article:
    title: str
    source: str
    published: str
    link: str
    query: str        # where it came from, e.g. "Google News: 芒草", "PTT Hiking: 芒草"
    detail: str = ""  # extra context: dates, place, coordinates, or a text excerpt


def _get(url: str, data: dict | None = None, attempts: int = 3) -> bytes:
    body = urllib.parse.urlencode(data).encode() if data else None
    headers = {"User-Agent": USER_AGENT, "Cookie": "over18=1"}
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=30) as r:
                return r.read()
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))


def _text(markup: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", BeautifulSoup(markup or "", "html.parser").get_text(" ")).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _today() -> date:
    return datetime.now(TAIWAN).date()


def google_news() -> list[Article]:
    articles = []
    for q in QUERIES:
        try:
            feed = feedparser.parse(_get(GOOGLE_NEWS_URL.format(q=quote(q))))
        except OSError:
            print(f"  Google News: skipped query after retries: {q}")
            continue
        for entry in feed.entries[:25]:
            # Google News titles look like "標題 - 來源媒體"
            articles.append(Article(
                title=html.unescape(re.sub(r"\s+-\s+[^-]+$", "", entry.title)).strip(),
                source=entry.get("source", {}).get("title", ""),
                published=entry.get("published", ""),
                link=entry.link,
                query=f"Google News: {q}",
            ))
    return articles


def tourism_events() -> list[Article]:
    """觀光署 official event open data: events running now or starting within the lookahead window."""
    archive = zipfile.ZipFile(io.BytesIO(_get(TOURISM_EVENTS_URL)))
    events = json.loads(archive.read("EventList.json").decode("utf-8-sig"))["Events"]
    today = _today()
    horizon = today + timedelta(days=EVENT_LOOKAHEAD_DAYS)
    articles = []
    for e in events:
        try:
            start = datetime.fromisoformat(e["StartDateTime"]).date()
            end = datetime.fromisoformat(e["EndDateTime"]).date()
        except (KeyError, TypeError, ValueError):
            continue
        if end < today or start > horizon or (end - start).days > EVENT_MAX_DAYS:
            continue
        if EVENT_SKIP_TITLES.search(e["EventName"]):
            continue
        place = "".join(filter(None, [(e.get("PostalAddress") or {}).get(k) for k in ("City", "Town")]))
        coords = f" ({e['PositionLat']:.4f},{e['PositionLon']:.4f})" if e.get("PositionLat") else ""
        articles.append(Article(
            title=e["EventName"],
            source="觀光署活動資料",
            published=start.isoformat(),
            link=e.get("WebsiteURL") or "",
            query="Official event listing",
            detail=f"{start}~{end} @ {place}{coords}. {_text(e.get('Description', ''), 100)}",
        ))
    return articles


def taipei_flowers() -> list[Article]:
    """花IN台北 (臺北市公園處): Taipei bloom news, e.g. 陽明山, 士林官邸."""
    data = json.loads(_get(TAIPEI_FLOWERS_URL, {"labelId": 0, "pageNum": 12, "nowPage": 1, "dataType": "NEWS"}))
    cutoff = (_today() - timedelta(days=RECENT_DAYS)).isoformat()
    return [Article(title=it["title"], source="花IN台北 (臺北市公園處)", published=it["date"], link=it["url"],
                    query="Official bloom news")
            for it in data["listData"] if it["date"] >= cutoff]


def national_parks() -> list[Article]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).isoformat()
    articles = []
    for name, host in NATIONAL_PARKS.items():
        try:
            data = json.loads(_get(f"https://{host}/sites/{host}/ch/home.json"))
        except (OSError, ValueError) as ex:
            print(f"  National parks: skipped {name}: {ex}")
            continue
        for key in ("newsList", "eventList", "chNewsList"):
            for it in data.get(key, []):
                if it.get("publish_up", "") < cutoff:
                    continue
                articles.append(Article(
                    title=it["title"], source=name, published=it["publish_up"][:10],
                    link=f"https://{host}/ch/", query="Official national park news",
                    detail=_text(it.get("content", "")),
                ))
    return articles


def forest_recreation() -> list[Article]:
    """林業保育署 forest recreation areas (阿里山, 太平山, 奧萬大...)."""
    cutoff = _today() - timedelta(days=RECENT_DAYS)
    articles = []
    for page in (0, 1):
        for it in json.loads(_get(FOREST_NEWS_URL.format(page=page)))["data"]:
            ms = int(re.search(r"\d+", it["ann_date"]).group())
            published = datetime.fromtimestamp(ms / 1000, TAIWAN).date()
            if published < cutoff:
                continue
            articles.append(Article(
                title=it["title"], source=f"林業保育署 {it.get('dep_name', '')}".strip(),
                published=published.isoformat(), link=urllib.parse.urljoin("https://recreation.forest.gov.tw", it["url"]),
                query="Official forest recreation news",
            ))
    return articles


def _ptt_excerpt(url: str) -> str:
    main = BeautifulSoup(_get(url), "html.parser").select_one("#main-content")
    if not main:
        return ""
    for tag in main.select(".article-metaline, .article-metaline-right, .push"):
        tag.decompose()
    return _text(main.get_text(" ").split("※ 發信站")[0], 200)


def ptt() -> list[Article]:
    """Recent posts on each board: walk index pages back until posts are older than PTT_DAYS."""
    cutoff = time.time() - PTT_DAYS * 86400
    articles = []
    for board in PTT_BOARDS:
        url = f"https://www.ptt.cc/bbs/{board}/index.html"
        for _ in range(PTT_MAX_PAGES):
            page = BeautifulSoup(_get(url), "html.parser")
            # Pinned posts sit below the separator; only the list above it is chronological
            sep = page.select_one("div.r-list-sep")
            rows = [r for r in page.select("div.r-ent") if not sep or r.sourceline < sep.sourceline]
            oldest = None
            for row in rows:
                a = row.select_one("div.title a")  # deleted posts have no link
                m = a and re.search(r"M\.(\d+)\.", a["href"])
                if not m:
                    continue
                posted = int(m.group(1))
                oldest = posted if oldest is None else min(oldest, posted)
                title = a.get_text(strip=True)
                if posted < cutoff or PTT_SKIP_TITLES.search(title):
                    continue
                link = urllib.parse.urljoin("https://www.ptt.cc", a["href"])
                try:
                    excerpt = _ptt_excerpt(link)
                except OSError:
                    excerpt = ""
                articles.append(Article(
                    title=title, source=f"PTT {board}",
                    published=datetime.fromtimestamp(posted, TAIWAN).date().isoformat(),
                    link=link, query=f"PTT {board} (first-hand report)", detail=excerpt,
                ))
            prev = page.find("a", string=re.compile("上頁"))
            if oldest is None or oldest < cutoff or not prev or not prev.get("href"):
                break
            url = urllib.parse.urljoin("https://www.ptt.cc", prev["href"])
    return articles


SOURCES = {
    "Google News": google_news,
    "觀光署活動": tourism_events,
    "花IN台北": taipei_flowers,
    "國家公園": national_parks,
    "森林遊樂區": forest_recreation,
    "PTT": ptt,
}


def fetch_articles() -> tuple[list[Article], dict[str, str]]:
    """Returns all items (deduplicated by title) and a per-source status line."""
    articles, status, seen = [], {}, set()
    for name, fetch in SOURCES.items():
        try:
            items = [a for a in fetch() if a.title not in seen]
            seen.update(a.title for a in items)
            articles += items
            status[name] = f"{len(items)} items"
        except Exception as ex:  # one broken source must not stop the run
            status[name] = f"FAILED: {type(ex).__name__}: {ex}"
        print(f"  {name}: {status[name]}")
    return articles, status


if __name__ == "__main__":
    items, _ = fetch_articles()
    for a in items:
        print(f"[{a.query}] {a.title} ({a.source}, {a.published}) {a.detail[:80]}")
