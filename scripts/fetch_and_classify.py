"""
Fetches ethics/corruption news from GDELT and classifies each article
using the Google Gemini API. Updates data/articles.json and archives
articles older than 30 days to data/archive/YYYY-MM.json.
"""

import json
import os
import hashlib
import time
import re
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DATA_FILE      = Path("data/articles.json")
ARCHIVE_DIR    = Path("data/archive")
GDELT_URL      = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_RECORDS    = 50   # per query; 2 queries = up to 100 articles/day for Gemini

# Short, GDELT-friendly queries — sourcelang:english must be in the query string
# (not a URL param) for reliable English filtering. Gemini filters relevance.
QUERIES = {
    "government": "corruption fraud bribery misconduct government official politician sourcelang:english",
    "nonprofit":  "corruption fraud embezzlement misconduct nonprofit charity NGO foundation sourcelang:english",
}

# ── GDELT fetch ───────────────────────────────────────────────────────────────
def fetch_gdelt(query: str, retries: int = 3) -> list[dict]:
    params = {
        "query":      query,
        "mode":       "ArtList",
        "maxrecords": MAX_RECORDS,
        "timespan":   "1d",
        "format":     "json",
        "sort":       "DateDesc",
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(GDELT_URL, params=params, timeout=30)
            if resp.status_code == 429:
                wait = 30 * attempt
                print(f"  [GDELT] Rate limited. Waiting {wait}s before retry {attempt}/{retries}...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json().get("articles") or []
        except Exception as e:
            print(f"  [GDELT error] attempt {attempt}/{retries}: {e}")
            if attempt < retries:
                time.sleep(15 * attempt)
    return []


# ── Gemini classification ──────────────────────────────────────────────────────
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
    "/models/gemini-1.5-flash-latest:generateContent?key={key}"
)

CLASSIFY_PROMPT = """Classify this news article. Respond with ONLY a JSON object — no markdown fences, no explanation.

Title: {title}
Source domain: {domain}

Return exactly this structure:
{{
  "sector":   "government" | "nonprofit" | "both" | "neither",
  "tone":     "negative" | "positive" | "neutral",
  "us_story": true | false,
  "relevant": true | false
}}

Definitions:
- sector:   Is this about ethics/corruption/integrity/accountability in government/public sector ("government"), nonprofits/charities/NGOs ("nonprofit"), both ("both"), or neither/unrelated ("neither")?
- tone:     "negative" = corruption, fraud, or misconduct story; "positive" = anti-corruption success, whistleblower win, accountability working; "neutral" = ambiguous
- us_story: Is this story primarily about events OCCURRING IN the United States? (true/false — not about where it was published)
- relevant: Is this genuinely about ethics, corruption, fraud, accountability, or integrity issues? (true/false — filter out unrelated articles)
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

    try:
        resp = requests.post(
            GEMINI_URL.format(key=GEMINI_API_KEY),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Strip any accidental markdown code fences
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

        return json.loads(raw)
    except Exception as e:
        print(f"  [Gemini error] {e}")
        return None


# ── Data helpers ───────────────────────────────────────────────────────────────
def article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

def parse_gdelt_date(seendate: str) -> str:
    try:
        return datetime.strptime(seendate[:8], "%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def load_articles() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"articles": []}

def save_articles(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def clean_title(title: str) -> str:
    """Remove common HTML entities and extra whitespace."""
    title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    title = title.replace("&quot;", '"').replace("&#39;", "'")
    return " ".join(title.split())

def archive_old_articles(data: dict) -> dict:
    """Move articles older than 30 days into monthly archive JSON files."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    active, to_archive = [], []

    for article in data["articles"]:
        (to_archive if article["date"] < cutoff else active).append(article)

    by_month: dict[str, list] = {}
    for article in to_archive:
        month_key = article["date"][:7]
        by_month.setdefault(month_key, []).append(article)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    for month_key, articles in by_month.items():
        archive_file = ARCHIVE_DIR / f"{month_key}.json"
        if archive_file.exists():
            with open(archive_file) as f:
                existing = json.load(f)
            existing_ids = {a["id"] for a in existing.get("articles", [])}
            new = [a for a in articles if a["id"] not in existing_ids]
            existing["articles"].extend(new)
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
    data        = load_articles()
    existing_ids: set[str] = {a["id"] for a in data["articles"]}
    seen_urls:   set[str]  = set()
    new_count = 0

    for query_label, query in QUERIES.items():
        print(f"\nQuerying GDELT [{query_label}]...")
        raw_articles = fetch_gdelt(query)
        print(f"  Received {len(raw_articles)} results.")
        time.sleep(10)  # polite pause between GDELT requests

        for raw in raw_articles:
            url = raw.get("url", "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            aid = article_id(url)
            if aid in existing_ids:
                continue

            title = clean_title(raw.get("title", ""))
            if not title:
                continue

            domain   = raw.get("domain", "")
            date_str = parse_gdelt_date(raw.get("seendate", ""))

            print(f"  Classifying: {title[:70]}...")
            result = classify_article(title, domain)
            time.sleep(0.6)  # stay well under Gemini's 15 req/min free limit

            if not result:
                continue
            if not result.get("relevant", False):
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
