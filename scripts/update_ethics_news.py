#!/usr/bin/env python3
"""Fetch ethics news, classify it, and maintain monthly archive snapshots."""

from __future__ import annotations

import json
import argparse
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = ROOT / "ethics-news"
CURRENT_PATH = APP_ROOT / "data" / "current.json"
ARCHIVE_DIR = APP_ROOT / "data" / "archive"
MONTHS_PATH = ARCHIVE_DIR / "months.json"

GOVERNMENT_QUERIES = [
    "government ethics",
    "public corruption",
    "public sector graft",
    "ethics commission investigation",
    "city council bribery",
    "federal corruption case",
    "public official indictment corruption",
    "inspector general ethics investigation",
    "public procurement fraud government",
    "county commissioner bribery",
    "state auditor corruption probe",
    "campaign finance ethics case",
]

NONPROFIT_QUERIES = [
    "nonprofit ethics",
    "charity corruption",
    "charity fraud case",
    "ngo corruption",
    "foundation embezzlement",
    "nonprofit governance reform",
]

POSITIVE_KEYWORDS = {
    "reform",
    "transparency",
    "oversight",
    "accountability",
    "watchdog",
    "watchdogs",
    "audit",
    "auditor",
    "auditors",
    "exposed",
    "exposes",
    "sentenced",
    "sentence",
    "prosecuted",
    "prosecution",
    "conviction",
    "convictions",
    "indicted",
    "reindicted",
    "pleaded guilty",
    "pleads guilty",
    "guilty plea",
    "anti-corruption",
    "anti corruption",
    "crackdown",
    "improve",
    "improved",
    "improves",
    "cleaned up",
    "cleared",
    "acquitted",
    "new ethics rules",
    "adopts ethics",
    "whistleblower protection",
}

NEGATIVE_KEYWORDS = {
    "corruption",
    "graft",
    "bribery",
    "bribe",
    "fraud",
    "embezzlement",
    "kickback",
    "money laundering",
    "scandal",
    "misuse",
    "misconduct",
    "cover-up",
    "cover up",
    "conflict of interest",
    "ethics violation",
    "ethics violations",
}

ACCOUNTABILITY_KEYWORDS = {
    "probe",
    "investigation",
    "charged",
    "arrested",
    "indicted",
    "reindicted",
    "convicted",
    "sentenced",
    "watchdog",
    "auditor",
    "audit",
    "oversight",
    "ethics commission",
    "inspector general",
    "raid",
    "raids",
    "crackdown",
}

GOVERNMENT_TERMS = {
    "government",
    "public",
    "municipal",
    "city",
    "state",
    "federal",
    "minister",
    "senate",
    "congress",
    "parliament",
    "mayor",
    "governor",
    "agency",
    "department",
    "county",
    "attorney general",
    "public official",
    "ethics commission",
    "inspector general",
    "prosecutor",
    "district attorney",
    "public schools",
    "school board",
    "procurement",
    "campaign finance",
    "ministerial",
}

NONPROFIT_TERMS = {
    "nonprofit",
    "non-profit",
    "non profit",
    "charity",
    "charitable",
    "foundation",
    "ngo",
    "non-governmental",
    "civil society",
    "not-for-profit",
    "not for profit",
    "philanthropy",
    "donor-funded",
    "association",
    "voluntary organization",
}

NONPROFIT_STRICT_TERMS = {
    "nonprofit",
    "non-profit",
    "non profit",
    "charity",
    "charitable",
    "foundation",
    "ngo",
    "non-governmental",
    "civil society",
    "not-for-profit",
    "not for profit",
    "philanthropy",
    "donor-funded",
}

GOVERNMENT_STRONG_TERMS = {
    "government",
    "public official",
    "attorney general",
    "inspector general",
    "ethics commission",
    "federal",
    "state",
    "county",
    "city council",
    "public schools",
    "school board",
    "district attorney",
    "campaign finance",
    "department of justice",
    "justice department",
    "prosecutor",
}

BUSINESS_TERMS = {
    "earnings",
    "quarterly results",
    "stock",
    "share price",
    "ipo",
    "merger",
    "acquisition",
    "ceo",
    "investor",
    "wall street",
}

US_TERMS = {
    "united states",
    "u.s.",
    "u.s",
    "us senate",
    "us congress",
    "department of justice",
    "doj",
    "federal",
    "state",
    "county",
    "attorney general",
    "irs",
    "supreme court",
    "justice department",
    "white house",
    "washington",
    "new york",
    "california",
    "texas",
    "florida",
    "illinois",
    "hawaii",
}

NON_US_TERMS = {
    "uk",
    "united kingdom",
    "england",
    "scotland",
    "wales",
    "ireland",
    "jamaica",
    "haiti",
    "brazil",
    "belgium",
    "india",
    "china",
    "mongolia",
    "lebanon",
    "france",
    "canada",
    "nigeria",
    "kenya",
    "philippines",
    "indonesia",
    "australia",
    "europe",
    "virgin islands",
}

US_SOURCE_HINTS = {
    "associated press",
    "ap news",
    "ohio capital journal",
    "wosu public media",
    "wkyc",
    "cleveland 19 news",
    "fox 8 news",
    "news 5 cleveland wews",
    "sacramento bee",
    "dallas news",
    "news on 6",
    "propublica",
    "bloomberg law news",
    "virgin islands daily news",
    "wosu",
    "kansas city star",
    "the center square",
    "honolulu civil beat",
}

NON_US_SOURCE_HINTS = {
    "bbc",
    "the age",
    "hungarian conservative",
    "focus taiwan",
    "malay mail",
    "the edge malaysia",
    "nst online",
    "the star",
    "citynews montreal",
    "devdiscourse",
}

MAX_STORIES_PER_COLUMN = 60
USER_AGENT = "ethics-news-board/2.0 (+https://github.com/rkchristensen/ethics_news_test)"


@dataclass
class Story:
    title: str
    short_title: str
    url: str
    source: str
    published_at: str
    sentiment: str
    government: bool
    nonprofit: bool
    region: str


def google_news_rss_url(query: str, start_date: date | None = None, end_date: date | None = None) -> str:
    query_parts = [query]
    if start_date:
        query_parts.append(f"after:{start_date.isoformat()}")
    if end_date:
        query_parts.append(f"before:{end_date.isoformat()}")
    encoded = urllib.parse.quote_plus(" ".join(query_parts))
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            insecure = ssl._create_unverified_context()
            with urllib.request.urlopen(request, timeout=20, context=insecure) as response:
                return response.read()
        raise


def parse_date(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def short_title(title: str, limit: int = 100) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def contains_any(text: str, terms: Iterable[str]) -> bool:
    for term in terms:
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, text):
            return True
    return False


def classify_sentiment(text: str) -> str | None:
    positive_hits = sum(1 for term in POSITIVE_KEYWORDS if re.search(r"\b" + re.escape(term) + r"\b", text))
    negative_hits = sum(1 for term in NEGATIVE_KEYWORDS if re.search(r"\b" + re.escape(term) + r"\b", text))
    accountability_hits = sum(1 for term in ACCOUNTABILITY_KEYWORDS if re.search(r"\b" + re.escape(term) + r"\b", text))

    if positive_hits == 0 and negative_hits == 0 and accountability_hits == 0:
        return None
    if accountability_hits > 0 and negative_hits > 0:
        return "positive"
    if positive_hits > negative_hits:
        return "positive"
    return "negative"


def infer_region(text: str, url: str) -> str:
    domain = urllib.parse.urlparse(url).netloc.lower()
    if contains_any(text, US_SOURCE_HINTS):
        return "us"
    if contains_any(text, NON_US_SOURCE_HINTS):
        return "non-us"
    if any(token in domain for token in ("nytimes.com", "washingtonpost.com", "bloomberglaw.com", "apnews.com", "propublica.org", "justice.gov")):
        return "us"
    if any(token in domain for token in ("wosu.org", "wkyc.com", "news5cleveland.com", "cleveland19.com", "newson6.com", "dallasnews.com", "sacbee.com")):
        return "us"
    if domain.endswith(".us"):
        return "us"
    if re.search(r"\.(uk|au|ca|in|ng|ke|fr|br|be|jm|ht|ph|id)\b", domain):
        return "non-us"
    if contains_any(text, US_TERMS):
        return "us"
    if contains_any(text, NON_US_TERMS):
        return "non-us"
    return "us" if ".gov" in domain or ".edu" in domain else "non-us"


def parse_rss_items(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = root.findall(".//item")
    parsed = []
    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()

        source_name = ""
        source_el = item.find("source")
        if source_el is not None and source_el.text:
            source_name = source_el.text.strip()
        if not source_name and " - " in title:
            source_name = title.rsplit(" - ", 1)[-1].strip()

        parsed.append(
            {
                "title": title,
                "url": link,
                "published_at": parse_date(pub_date),
                "source": source_name or "Unknown source",
            }
        )
    return parsed


def should_skip_business_only(text: str) -> bool:
    has_business = contains_any(text, BUSINESS_TERMS)
    has_relevant_domain = contains_any(text, GOVERNMENT_TERMS) or contains_any(text, NONPROFIT_TERMS)
    return has_business and not has_relevant_domain


def normalize_story(raw: dict, default_government: bool, default_nonprofit: bool) -> Story | None:
    if not raw["title"] or not raw["url"]:
        return None

    text = f'{raw["title"]} {raw["source"]}'.lower()
    if should_skip_business_only(text):
        return None

    sentiment = classify_sentiment(text)
    if sentiment is None:
        return None

    is_government = contains_any(text, GOVERNMENT_TERMS)
    is_nonprofit = contains_any(text, NONPROFIT_TERMS)
    has_strict_nonprofit = contains_any(text, NONPROFIT_STRICT_TERMS)
    has_strong_government = contains_any(text, GOVERNMENT_STRONG_TERMS)

    if not is_government and not is_nonprofit:
        is_government = default_government
        is_nonprofit = default_nonprofit

    if default_nonprofit and not has_strict_nonprofit:
        return None

    if is_nonprofit and not has_strict_nonprofit:
        is_nonprofit = False

    if is_nonprofit and has_strong_government and not has_strict_nonprofit:
        is_nonprofit = False

    if not is_government and default_government:
        is_government = True

    if not is_government and not is_nonprofit:
        return None

    region = infer_region(text, raw["url"])

    return Story(
        title=raw["title"],
        short_title=short_title(raw["title"]),
        url=raw["url"],
        source=raw["source"],
        published_at=raw["published_at"].isoformat(),
        sentiment=sentiment,
        government=is_government,
        nonprofit=is_nonprofit,
        region=region,
    )


def collect_stories(start_date: date | None = None, end_date: date | None = None) -> list[Story]:
    collected: list[Story] = []
    seen_urls: set[str] = set()
    grouped_queries = (
        [(query, True, False) for query in GOVERNMENT_QUERIES]
        + [(query, False, True) for query in NONPROFIT_QUERIES]
    )

    for query, default_government, default_nonprofit in grouped_queries:
        try:
            feed_xml = fetch(google_news_rss_url(query, start_date=start_date, end_date=end_date))
        except Exception:
            continue

        for item in parse_rss_items(feed_xml):
            if item["url"] in seen_urls:
                continue
            story = normalize_story(item, default_government, default_nonprofit)
            if story is None:
                continue
            seen_urls.add(item["url"])
            collected.append(story)

    return sorted(collected, key=lambda story: story.published_at, reverse=True)


def story_to_dict(story: Story) -> dict:
    return {
        "title": story.title,
        "short_title": story.short_title,
        "url": story.url,
        "source": story.source,
        "published_at": story.published_at,
        "sentiment": story.sentiment,
        "region": story.region,
    }


def build_snapshot(stories: list[Story], label: str | None = None) -> dict:
    government = [story_to_dict(story) for story in stories if story.government][:MAX_STORIES_PER_COLUMN]
    nonprofit = [story_to_dict(story) for story in stories if story.nonprofit][:MAX_STORIES_PER_COLUMN]
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "government": government,
        "nonprofit": nonprofit,
    }
    if label:
        payload["label"] = label
    return payload


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def unique_month_stories(days: dict) -> dict:
    government_map: dict[str, dict] = {}
    nonprofit_map: dict[str, dict] = {}
    for snapshot in days.values():
        for story in snapshot.get("government", []):
            government_map.setdefault(story["url"], story)
        for story in snapshot.get("nonprofit", []):
            nonprofit_map.setdefault(story["url"], story)

    government = sorted(government_map.values(), key=lambda story: story["published_at"], reverse=True)
    nonprofit = sorted(nonprofit_map.values(), key=lambda story: story["published_at"], reverse=True)
    return {"government": government, "nonprofit": nonprofit}


def update_archive(current_payload: dict, snapshot_date: date | None = None, month_key_override: str | None = None) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_day = snapshot_date or datetime.now(timezone.utc).date()
    snapshot_date_str = snapshot_day.isoformat()
    month_key = month_key_override or snapshot_date_str[:7]
    month_path = ARCHIVE_DIR / f"{month_key}.json"

    month_data = load_json(
        month_path,
        {
            "month": month_key,
            "label": format_month_label(month_key),
            "updated_at": current_payload["updated_at"],
            "days": {},
            "government": [],
            "nonprofit": [],
        },
    )
    month_data["updated_at"] = current_payload["updated_at"]
    month_data["days"][snapshot_date_str] = {
        "updated_at": current_payload["updated_at"],
        "government": current_payload["government"],
        "nonprofit": current_payload["nonprofit"],
    }
    month_unique = unique_month_stories(month_data["days"])
    month_data["government"] = month_unique["government"]
    month_data["nonprofit"] = month_unique["nonprofit"]
    month_path.write_text(json.dumps(month_data, indent=2), encoding="utf-8")

    months_payload = load_json(MONTHS_PATH, {"months": []})
    months = [month for month in months_payload.get("months", []) if isinstance(month, str)]
    if month_key not in months:
        months.append(month_key)
    months.sort(reverse=True)
    MONTHS_PATH.write_text(json.dumps({"months": months}, indent=2), encoding="utf-8")


def format_month_label(month_key: str) -> str:
    year, month = month_key.split("-")
    parsed = datetime(int(year), int(month), 1, tzinfo=timezone.utc)
    return parsed.strftime("%B %Y")


def month_window(month_key: str) -> tuple[date, date]:
    year, month = [int(part) for part in month_key.split("-")]
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill-month", action="append", default=[], help="Month to backfill in YYYY-MM format")
    return parser.parse_args()


def run_current_refresh() -> None:
    stories = collect_stories()
    current_payload = build_snapshot(stories)
    CURRENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CURRENT_PATH.write_text(json.dumps(current_payload, indent=2), encoding="utf-8")
    update_archive(current_payload)
    print(
        f"Wrote {CURRENT_PATH} with {len(current_payload['government'])} government and "
        f"{len(current_payload['nonprofit'])} nonprofit stories."
    )


def run_backfill(month_key: str) -> None:
    start_date, end_date = month_window(month_key)
    stories = collect_stories(start_date=start_date, end_date=end_date)
    payload = build_snapshot(stories, label=format_month_label(month_key))
    synthetic_snapshot_date = end_date - timedelta(days=1)
    update_archive(payload, snapshot_date=synthetic_snapshot_date, month_key_override=month_key)
    print(
        f"Backfilled {month_key} with {len(payload['government'])} government and "
        f"{len(payload['nonprofit'])} nonprofit stories."
    )


if __name__ == "__main__":
    args = parse_args()
    for month_key in args.backfill_month:
        run_backfill(month_key)
    run_current_refresh()
