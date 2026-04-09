"""
Fetches ethics/corruption news via Google News RSS (aggregates thousands of
sources, works from GitHub Actions) and classifies each article using the
Google Gemini API. Updates data/articles.json and archives articles older
than 30 days to data/archive/YYYY-MM.json.
"""

from __future__ import annotations

import json
import os
import hashlib
import re
import ssl
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DATA_FILE      = Path("data/articles.json")
ARCHIVE_DIR    = Path("data/archive")
USER_AGENT     = "ethics-news-board/1.0"

# ── Google News RSS queries ───────────────────────────────────────────────────
# Each query returns up to ~10 recent results from thousands of global sources.
GOVERNMENT_QUERIES = [
    "government corruption",
    "public corruption indicted",
    "government official fraud",
    "public sector bribery",
    "city council corruption",
    "politician misconduct",
    "federal corruption case",
    "ethics commission investigation",
    "government official charged",
    "public official embezzlement",
    "government graft",
    "government whistleblower",
    "government accountability ethics",
    "government official kickback",
    "municipal corruption arrested",
]

NONPROFIT_QUERIES = [
    "nonprofit corruption",
    "charity fraud",
    "ngo corruption",
    "charity embezzlement",
    "foundation misconduct",
    "nonprofit misappropriation",
    "charity accountability",
    "nonprofit ethics violation",
    "aid organization fraud",
    "nonprofit governance scandal",
]

# ── Keyword pre-filter (avoids burning Gemini quota on irrelevant stories) ────
ETHICS_KEYWORDS = {
    "corrupt", "brib", "fraud", "embezzl", "graft", "kickback",
    "misconduct", "malfeasance", "scandal", "indicted", "convicted",
    "charged", "arrested", "probe", "investigation", "misappropriat",
    "extortion", "money launder", "abuse of power", "ethics",
    "whistleblow", "accountability", "transparency", "self-dealing",
    "nepotism", "cronyism", "conflict of interest", "reform",
}


# ── Google News RSS fetch ─────────────────────────────────────────────────────
def google_news_url(query: str) -> str:
    encoded = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"


def fetch_url(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                return r.read()
        raise


def parse_rss(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    results = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url   = (item.findtext("link")  or "").strip()
        pub   = (item.findtext("pubDate") or "").strip()

        # Google News puts the outlet name in <source>
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        if not source and " - " in title:
            source = title.rsplit(" - ", 1)[-1].strip()

        if title and url:
            results.append({"title": title, "url": url, "pub": pub, "source": source})
    return results


def parse_date(raw: str) -> str:
    try:
        return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def is_ethics_related(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in ETHICS_KEYWORDS)


def clean(s: str) -> str:
    return " ".join(s.replace("&amp;", "&").replace("&#39;", "'")
                     .replace("&quot;", '"').split())


# ── Gemini classification ──────────────────────────────────────────────────────
import urllib.request as _ur

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
    "/models/gemini-1.5-flash-latest:generateContent?key={key}"
)

CLASSIFY_PROMPT = """Classify this news article. Respond with ONLY a JSON object — no markdown, no extra text.

Title: {title}
Source: {source}

Return exactly:
{{
  "sector":   "government" | "nonprofit" | "both" | "neither",
  "tone":     "negative" | "positive" | "neutral",
  "us_story": true | false,
  "relevant": true | false
}}

- sector:   government/public sector, nonprofit/charity/NGO, both, or neither
- tone:     negative=corruption/fraud/misconduct, positive=accountability/reform/anti-corruption win, neutral=ambiguous
- us_story: true if the story is primarily about events IN the United States
- relevant: true if genuinely about ethics, corruption, fraud, accountability, or integrity
"""

def classify(title: str, source: str) -> dict | None:
    if not GEMINI_API_KEY:
        return None
    prompt  = CLASSIFY_PROMPT.format(title=title, source=source)
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 150},
    }).encode()
    url = GEMINI_URL.format(key=GEMINI_API_KEY)
    for attempt in range(1, 4):
        try:
            req  = urllib.request.Request(url, data=payload,
                                          headers={"Content-Type": "application/json"},
                                          method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read())
            raw = body["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$",       "", raw)
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
    active, old = [], []
    for a in data["articles"]:
        (old if a["date"] < cutoff else active).append(a)

    by_month: dict[str, list] = {}
    for a in old:
        by_month.setdefault(a["date"][:7], []).append(a)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    for month, articles in by_month.items():
        f = ARCHIVE_DIR / f"{month}.json"
        if f.exists():
            existing = json.loads(f.read_text())
            seen = {a["id"] for a in existing.get("articles", [])}
            existing["articles"].extend(a for a in articles if a["id"] not in seen)
            f.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
        else:
            f.write_text(json.dumps({"articles": articles}, indent=2, ensure_ascii=False))

    data["articles"] = active
    return data


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=== Ethics News Fetch & Classify ===")
    data         = load_articles()
    existing_ids = {a["id"] for a in data["articles"]}
    seen_urls:   set[str] = set()
    new_count    = 0

    all_queries = (
        [(q, "government") for q in GOVERNMENT_QUERIES] +
        [(q, "nonprofit")  for q in NONPROFIT_QUERIES]
    )

    for query, default_sector in all_queries:
        print(f"\nQuery [{default_sector}]: {query}")
        try:
            xml_bytes = fetch_url(google_news_url(query))
            items     = parse_rss(xml_bytes)
        except Exception as e:
            print(f"  [Fetch error] {e}")
            continue
        print(f"  {len(items)} results")

        for item in items:
            url = item["url"]
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            aid = article_id(url)
            if aid in existing_ids:
                continue

            title  = clean(item["title"])
            source = clean(item["source"])
            date   = parse_date(item["pub"])

            if not is_ethics_related(title):
                continue

            print(f"  Classifying: {title[:70]}...")
            result = classify(title, source)
            time.sleep(0.6)

            if not result or not result.get("relevant"):
                continue
            sector = result.get("sector", "neither")
            if sector == "neither":
                continue

            data["articles"].append({
                "id":         aid,
                "url":        url,
                "title":      title,
                "source":     source,
                "date":       date,
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
