"""
Fetches ethics/corruption news from curated RSS feeds and classifies
each article using the Google Gemini API. Updates data/articles.json
and archives articles older than 30 days to data/archive/YYYY-MM.json.
"""

import json
import os
import hashlib
import time
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import requests

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DATA_FILE      = Path("data/articles.json")
ARCHIVE_DIR    = Path("data/archive")

# ── Curated RSS feeds ─────────────────────────────────────────────────────────
# Mix of ethics-specific outlets and general news filtered by keywords.
RSS_FEEDS = [
    # Investigative / corruption-specific
    "https://feeds.propublica.org/propublica/main",
    "https://occrp.org/en/feed",
    "https://www.theguardian.com/world/corruption/rss",
    "https://www.theguardian.com/politics/ethics/rss",

    # General news (high-quality, broad coverage)
    "https://feeds.reuters.com/reuters/topNews",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.politico.com/politics-news.xml",
    "https://thehill.com/feed/",
    "https://www.govexec.com/rss/all/",

    # Finance / accountability
    "https://www.opensecrets.org/news/feed",

    # Nonprofit / philanthropy
    "https://nonprofitquarterly.org/feed/",
    "https://www.philanthropy.com/feed",

    # International accountability
    "https://www.transparency.org/en/news/feed",
    "https://globalintegrity.org/feed/",
]

# Keyword filter — at least one must appear in title or description
ETHICS_KEYWORDS = [
    "corrupt", "brib", "fraud", "embezzl", "graft", "kickback",
    "misconduct", "malfeasance", "scandal", "indicted", "convicted",
    "ethics", "conflict of interest", "whistleblow", "accountability",
    "transparency", "anticorrupt", "anti-corrupt", "misappropriat",
    "extortion", "money launder", "abuse of power", "integrity violation",
    "self-dealing", "pay-to-play", "bid rigging", "ghost employee",
    "nepotism", "cronyism",
]


# ── RSS fetch & parse ─────────────────────────────────────────────────────────
def fetch_feed(url: str) -> list[dict]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; EthicsNewsBot/1.0)"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"  [Feed error] {url}: {e}")
        return []

    # Handle both RSS <channel><item> and Atom <entry>
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns)

    articles = []
    for item in items:
        def text(tag, fallback=""):
            el = item.find(tag) or item.find(f"atom:{tag}", ns)
            return (el.text or "").strip() if el is not None else fallback

        title = text("title")
        link  = text("link") or text("guid")

        # Atom <link> uses href attribute
        if not link:
            el = item.find("atom:link", ns)
            link = el.get("href", "") if el is not None else ""

        pub_date = text("pubDate") or text("published") or text("updated")
        desc     = re.sub(r"<[^>]+>", " ", text("description") or text("summary"))

        if title and link:
            articles.append({
                "title":    clean_text(title),
                "url":      link.strip(),
                "desc":     clean_text(desc)[:300],
                "pub_date": pub_date,
            })
    return articles


def clean_text(s: str) -> str:
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return " ".join(s.split())


def parse_date(raw: str) -> str:
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:19], fmt[:len(raw[:19])]).strftime("%Y-%m-%d")
        except Exception:
            continue
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def is_ethics_related(title: str, desc: str) -> bool:
    text = (title + " " + desc).lower()
    return any(kw in text for kw in ETHICS_KEYWORDS)


def domain_from_url(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else url


# ── Gemini classification ──────────────────────────────────────────────────────
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
    "/models/gemini-1.5-flash-latest:generateContent?key={key}"
)

CLASSIFY_PROMPT = """Classify this news article. Respond with ONLY a JSON object — no markdown, no explanation.

Title: {title}
Source: {domain}

Return exactly this structure:
{{
  "sector":   "government" | "nonprofit" | "both" | "neither",
  "tone":     "negative" | "positive" | "neutral",
  "us_story": true | false,
  "relevant": true | false
}}

Definitions:
- sector:   Is this about ethics/corruption/integrity/accountability in government/public sector ("government"), nonprofits/charities/NGOs ("nonprofit"), both ("both"), or neither ("neither")?
- tone:     "negative" = corruption/fraud/misconduct story; "positive" = anti-corruption success, whistleblower win, accountability working; "neutral" = ambiguous
- us_story: Is this story primarily about events OCCURRING IN the United States?
- relevant: Is this genuinely about ethics, corruption, fraud, accountability, or integrity? Filter out unrelated articles.
"""

def classify_article(title: str, domain: str) -> dict | None:
    if not GEMINI_API_KEY:
        print("  [Error] GEMINI_API_KEY not set.")
        return None

    prompt = CLASSIFY_PROMPT.format(title=title, domain=domain)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 150},
    }
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                GEMINI_URL.format(key=GEMINI_API_KEY),
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            return json.loads(raw)
        except Exception as e:
            print(f"  [Gemini error] attempt {attempt}/3: {e}")
            if attempt < 3:
                time.sleep(5 * attempt)
    return None


# ── Data helpers ───────────────────────────────────────────────────────────────
def article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

def load_articles() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"articles": []}

def save_articles(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def archive_old_articles(data: dict) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    active, to_archive = [], []
    for article in data["articles"]:
        (to_archive if article["date"] < cutoff else active).append(article)

    by_month: dict[str, list] = {}
    for article in to_archive:
        by_month.setdefault(article["date"][:7], []).append(article)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    for month_key, articles in by_month.items():
        archive_file = ARCHIVE_DIR / f"{month_key}.json"
        if archive_file.exists():
            with open(archive_file) as f:
                existing = json.load(f)
            existing_ids = {a["id"] for a in existing.get("articles", [])}
            existing["articles"].extend(a for a in articles if a["id"] not in existing_ids)
            with open(archive_file, "w") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        else:
            with open(archive_file, "w") as f:
                json.dump({"articles": articles}, f, indent=2, ensure_ascii=False)

    data["articles"] = active
    return data


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=== Ethics News Fetch & Classify ===")
    data         = load_articles()
    existing_ids = {a["id"] for a in data["articles"]}
    seen_urls:   set[str] = set()
    new_count = 0

    for feed_url in RSS_FEEDS:
        print(f"\nFetching: {feed_url}")
        items = fetch_feed(feed_url)
        print(f"  Got {len(items)} items.")

        for item in items:
            url = item["url"]
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            aid = article_id(url)
            if aid in existing_ids:
                continue

            title = item["title"]
            if not title:
                continue

            # Quick keyword pre-filter to avoid wasting Gemini calls
            if not is_ethics_related(title, item["desc"]):
                continue

            domain   = domain_from_url(url)
            date_str = parse_date(item["pub_date"])

            print(f"  Classifying: {title[:70]}...")
            result = classify_article(title, domain)
            time.sleep(0.6)  # stay under Gemini free tier rate limit

            if not result or not result.get("relevant"):
                continue

            sector = result.get("sector", "neither")
            if sector == "neither":
                continue

            data["articles"].append({
                "id":         aid,
                "url":        url,
                "title":      title,
                "source":     domain,
                "date":       date_str,
                "sector":     sector,
                "tone":       result.get("tone", "neutral"),
                "us_story":   bool(result.get("us_story", False)),
                "added_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })
            existing_ids.add(aid)
            new_count += 1

    data = archive_old_articles(data)
    save_articles(data)
    print(f"\nDone. {new_count} new article(s) added. {len(data['articles'])} active total.")


if __name__ == "__main__":
    main()
