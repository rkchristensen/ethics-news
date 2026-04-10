"""
Fetches ethics/corruption news via Google News RSS and classifies each
article using keyword matching (fast, free, no API needed).
Updates data/articles.json and archives articles older than 30 days.
"""

from __future__ import annotations

import json
import hashlib
import re
import ssl
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
import os, time
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DATA_FILE   = Path("data/articles.json")
ARCHIVE_DIR = Path("data/archive")
USER_AGENT  = "ethics-news-board/1.0"
MAX_PER_COL = 60   # max articles per column to keep active

# ── Google News RSS queries ───────────────────────────────────────────────────
GOVERNMENT_QUERIES = [
    "government corruption",
    "public official corruption",
    "government fraud indicted",
    "public sector bribery",
    "city council corruption",
    "politician misconduct",
    "federal corruption case",
    "ethics commission investigation",
    "government whistleblower",
    "government accountability ethics",
]

NONPROFIT_QUERIES = [
    "nonprofit corruption",
    "charity fraud",
    "ngo corruption",
    "charity embezzlement",
    "nonprofit misconduct",
    "foundation fraud scandal",
    "nonprofit accountability",
    "charity misappropriation",
]

# ── Classification keywords ───────────────────────────────────────────────────
NEGATIVE_KEYWORDS = {
    "corrupt", "corruption", "bribery", "bribe", "fraud", "embezzl",
    "graft", "kickback", "money launder", "scandal", "probe",
    "indicted", "convicted", "arrested", "charged", "misconduct",
    "malfeasance", "misappropriat", "extortion", "self-dealing",
    "nepotism", "cronyism", "racketeering", "misuse of funds",
    "breach of trust", "abuse of power", "conflict of interest",
    "pay-to-play", "bid rigging", "ghost employee",
}

POSITIVE_KEYWORDS = {
    "anti-corruption", "anticorruption", "reform", "transparency",
    "oversight", "accountability", "acquitted", "cleared",
    "whistleblower", "new ethics rules", "ethics reform",
    "strengthens ethics", "adopts ethics", "ethics overhaul",
    "good governance", "integrity award", "conviction overturned",
}

GOVERNMENT_TERMS = {
    "government", "municipal", "city", "state", "federal", "minister",
    "senate", "congress", "parliament", "mayor", "governor", "agency",
    "department", "county", "official", "politician", "council",
    "commissioner", "bureaucrat", "regulator", "police", "judiciary",
    "lawmaker", "legislat", "public sector", "public office",
    "attorney general", "prosecutor", "administration",
    # Regulatory & law enforcement agencies
    "sec ", "f.b.i", "fbi", "irs", "doj", "dhs", "epa", "fda", "ftc",
    "cftc", "ofac", "interpol", "europol", "hmrc", "nato",
    "securities commission", "revenue service", "treasury",
    "u.s. attorney", "district attorney", "state attorney",
    "inspector general", "ethics office", "auditor general",
    "comptroller", "ombudsman", "anticorruption commission",
    "anti-corruption commission", "anti-corruption bureau",
    # Courts & law
    "court", "judge", "indictment", "grand jury", "plea", "sentenc",
    "convicted", "acquitted", "trial", "verdict",
    # International government bodies
    "ministry", "cabinet", "prefecture", "municipality", "borough",
    "ward", "district", "province", "prefecture",
}

NONPROFIT_TERMS = {
    "nonprofit", "non-profit", "charity", "foundation", "ngo",
    "not-for-profit", "philanthropy", "charitable", "aid organization",
    "relief organization", "advocacy group", "civic organization",
    "endowment", "501(c)",
}

US_TERMS = {
    "u.s.", "united states", "american", "washington d.c.",
    "congress", "senate", "white house", "fbi", "doj", "irs",
    "department of justice", "u.s. attorney", "federal bureau",
    # US states (partial match — covered by "in" check below)
    "alabama", "alaska", "arizona", "arkansas", "california",
    "colorado", "connecticut", "delaware", "florida", "georgia",
    "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
    "kentucky", "louisiana", "maine", "maryland", "massachusetts",
    "michigan", "minnesota", "mississippi", "missouri", "montana",
    "nebraska", "nevada", "new hampshire", "new jersey", "new mexico",
    "new york", "north carolina", "north dakota", "ohio", "oklahoma",
    "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "west virginia", "wisconsin", "wyoming",
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


def clean(s: str) -> str:
    return " ".join(
        s.replace("&amp;", "&").replace("&#39;", "'")
         .replace("&quot;", '"').replace("&nbsp;", " ").split()
    )


# ── Keyword classification (instant, no API) ──────────────────────────────────
def contains_any(text: str, terms: set[str]) -> bool:
    return any(t in text for t in terms)


def classify_tone(text: str) -> str:
    if contains_any(text, NEGATIVE_KEYWORDS):
        return "negative"
    if contains_any(text, POSITIVE_KEYWORDS):
        return "positive"
    return "neutral"


def classify_sector(text: str, default: str) -> str:
    is_gov = contains_any(text, GOVERNMENT_TERMS)
    is_ngo = contains_any(text, NONPROFIT_TERMS)
    if is_gov and is_ngo:
        return "both"
    if is_gov:
        return "government"
    if is_ngo:
        return "nonprofit"
    return default   # fall back to whichever query found it


def classify_us(text: str) -> bool:
    return contains_any(text, US_TERMS)


def is_relevant(text: str) -> bool:
    """Must contain at least one ethics/corruption keyword."""
    return contains_any(text, NEGATIVE_KEYWORDS | POSITIVE_KEYWORDS)


def is_business_only(text: str) -> bool:
    """Skip pure finance/business stories with no public-sector angle."""
    business = {"earnings", "quarterly results", "stock price", "share price",
                "ipo", "merger", "acquisition", "wall street", "nasdaq", "dow jones"}
    has_business = contains_any(text, business)
    has_public   = contains_any(text, GOVERNMENT_TERMS | NONPROFIT_TERMS)
    return has_business and not has_public


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


# ── Gemini one-line summary ───────────────────────────────────────────────────
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
    "/models/gemini-2.0-flash:generateContent?key={key}"
)

SUMMARY_PROMPT = """You are a news editor. Given a news headline, write exactly one sentence of background context.

Rules:
- Do NOT restate or paraphrase the headline — add new information
- Include relevant context: who is involved, what the broader case is about, what agency/jurisdiction, or why it matters
- Be specific and factual
- Do not start with "This article", "The headline", or "This story"
- Maximum 35 words

Headline: {title}
Source: {source}

Reply with only the one sentence, no quotes, no punctuation other than the sentence itself."""

def generate_summary(title: str, source: str) -> str:
    if not GEMINI_API_KEY:
        return ""
    prompt  = SUMMARY_PROMPT.format(title=title, source=source)
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 80},
    }).encode()
    url = GEMINI_URL.format(key=GEMINI_API_KEY)
    for attempt in range(1, 3):
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read())
            text = body["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Strip surrounding quotes if Gemini added them
            return text.strip('"').strip("'")
        except Exception as e:
            print(f"  [Gemini summary error] attempt {attempt}: {e}")
            if attempt < 2:
                time.sleep(3)
    return ""


def backfill_summaries(data: dict, max_per_run: int = 20) -> int:
    """Add summaries to articles missing one, up to max_per_run per run."""
    count = 0
    for article in data["articles"]:
        if count >= max_per_run:
            break
        if article.get("summary"):
            continue
        summary = generate_summary(article["title"], article["source"])
        time.sleep(0.6)
        if summary:
            article["summary"] = summary
            count += 1
    return count


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
            text   = title.lower()

            if not is_relevant(text) or is_business_only(text):
                continue

            sector = classify_sector(text, default_sector)
            tone   = classify_tone(text)
            us     = classify_us(text)
            date   = parse_date(item["pub"])

            data["articles"].append({
                "id":         aid,
                "url":        url,
                "title":      title,
                "source":     source,
                "date":       date,
                "sector":     sector,
                "tone":       tone,
                "us_story":   us,
                "summary":    "",
                "added_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })
            existing_ids.add(aid)
            new_count += 1

    # Trim to MAX_PER_COL per sector (keep newest)
    data["articles"].sort(key=lambda a: a["date"], reverse=True)
    gov_seen, ngo_seen = 0, 0
    trimmed = []
    for a in data["articles"]:
        s = a["sector"]
        if s in ("government", "both"):
            if gov_seen >= MAX_PER_COL:
                continue
            gov_seen += 1
        if s in ("nonprofit", "both"):
            if ngo_seen >= MAX_PER_COL:
                continue
            ngo_seen += 1
        trimmed.append(a)
    data["articles"] = trimmed

    # Backfill summaries AFTER trimming — only for the articles we actually keep
    if GEMINI_API_KEY:
        missing = sum(1 for a in data["articles"] if not a.get("summary"))
        if missing:
            print(f"\nBackfilling summaries for up to 10 of {missing} article(s)...")
            filled = backfill_summaries(data, max_per_run=10)
            print(f"  Filled {filled} summaries.")

    data = archive_old_articles(data)
    save_articles(data)
    print(f"\nDone. {new_count} new article(s) added. {len(data['articles'])} active total.")


if __name__ == "__main__":
    main()
