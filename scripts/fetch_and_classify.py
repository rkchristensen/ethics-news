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
RSS_FEEDS = [

    # ── Investigative & watchdog (global) ─────────────────────────────────────
    "https://feeds.propublica.org/propublica/main",           # ProPublica (US)
    "https://occrp.org/en/feed",                             # OCCRP (global corruption)
    "https://www.icij.org/feed/",                            # ICIJ (Panama Papers etc.)
    "https://theintercept.com/feed/?rss",                    # The Intercept
    "https://insightcrime.org/feed/",                        # InSight Crime (Latin America)
    "https://www.citizensforethics.org/feed/",               # CREW
    "https://whistleblower.org/feed/",                       # Govt Accountability Project
    "https://gfintegrity.org/feed/",                         # Global Financial Integrity
    "https://taxjustice.net/feed/",                          # Tax Justice Network
    "https://www.globalwitness.org/en/news/feed/",           # Global Witness
    "https://www.bellingcat.com/feed/",                      # Bellingcat
    "https://www.muckrock.com/news/feed/",                   # MuckRock (FOIA)
    "https://www.corruptionwatch.org.za/feed/",              # Corruption Watch (S. Africa)
    "https://balkaninsight.com/feed/",                       # BIRN (Balkans corruption)

    # ── Anti-corruption & transparency organizations ───────────────────────────
    "https://www.transparency.org/en/news/feed",             # Transparency International
    "https://globalintegrity.org/feed/",                     # Global Integrity
    "https://www.opensecrets.org/news/feed",                 # OpenSecrets

    # ── Guardian (dedicated ethics/corruption/fraud tags) ─────────────────────
    "https://www.theguardian.com/world/corruption/rss",
    "https://www.theguardian.com/politics/ethics/rss",
    "https://www.theguardian.com/global-development/aid/rss",
    "https://www.theguardian.com/world/fraud/rss",
    "https://www.theguardian.com/us-news/rss",
    "https://www.theguardian.com/world/rss",

    # ── US national news ───────────────────────────────────────────────────────
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.politico.com/politics-news.xml",
    "https://thehill.com/feed/",
    "https://www.govexec.com/rss/all/",
    "https://www.federaltimes.com/feed/",
    "https://rollcall.com/feed/",
    "https://www.route-fifty.com/feed",
    "https://feeds.npr.org/1001/rss.xml",
    "https://www.motherjones.com/feed/",
    "https://www.thenation.com/feed/?post_type=article",
    "https://apnews.com/apf-topnews",                        # AP News
    "https://www.washingtonpost.com/rss/politics",
    "https://rss.nytimes.com/services/xml/rss/nf/US.xml",

    # ── UK & Ireland ──────────────────────────────────────────────────────────
    "https://www.independent.co.uk/news/world/rss",
    "https://www.opendemocracy.net/en/rss.xml",
    "https://bylinetimes.com/feed/",

    # ── Europe ────────────────────────────────────────────────────────────────
    "https://www.euractiv.com/feed/",
    "https://www.politico.eu/feed/",
    "https://www.spiegel.de/international/index.rss",        # Der Spiegel (English)
    "https://euobserver.com/rss.xml",

    # ── Africa ────────────────────────────────────────────────────────────────
    "https://mg.co.za/feed/",                                # Mail & Guardian (S. Africa)
    "https://www.premiumtimesng.com/feed/",                  # Premium Times (Nigeria)
    "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
    "https://www.theeastafrican.co.ke/tea/rss",              # The East African
    "https://www.nation.africa/kenya/rss.xml",               # Daily Nation (Kenya)

    # ── Asia & Pacific ────────────────────────────────────────────────────────
    "https://www.scmp.com/rss/91/feed",                      # South China Morning Post
    "https://www.thehindu.com/news/feeder/default.rss",      # The Hindu (India)
    "https://asia.nikkei.com/rss/feed/nar",                  # Nikkei Asia
    "https://www.bangkokpost.com/rss/data/topstories.xml",   # Bangkok Post
    "https://www.dawn.com/feeds/home",                       # Dawn (Pakistan)
    "https://www.abc.net.au/news/feed/51120/rss.xml",        # ABC Australia
    "https://www.smh.com.au/rss/feed.xml",                   # Sydney Morning Herald
    "https://www.straitstimes.com/news/world/rss.xml",       # Straits Times (Singapore)
    "https://www.rappler.com/feed/",                         # Rappler (Philippines)

    # ── Latin America ─────────────────────────────────────────────────────────
    "https://english.elpais.com/rss/",                       # El País English
    "https://apublica.org/feed/",                            # Agência Pública (Brazil)
    "https://www.ticotimes.net/feed",                        # Tico Times (Costa Rica)
    "https://mexiconewsdaily.com/feed/",                     # Mexico News Daily

    # ── Middle East ───────────────────────────────────────────────────────────
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.arabnews.com/rss.xml",
    "https://www.jordantimes.com/rss.xml",
    "https://www.middleeasteye.net/rss",                     # Middle East Eye

    # ── Canada ────────────────────────────────────────────────────────────────
    "https://www.cbc.ca/cmlink/rss-topstories",
    "https://www.theglobeandmail.com/arc/outboundfeeds/rss/",
    "https://nationalpost.com/feed/",

    # ── International broadcasters ────────────────────────────────────────────
    "https://rss.dw.com/rdf/rss-en-all",                     # Deutsche Welle
    "https://www.france24.com/en/rss",
    "https://www.voanews.com/api/z-mq_qei-qq/feed.rss",     # Voice of America
    "https://www.rfi.fr/en/rss",                             # Radio France Intl
    "https://www.euronews.com/rss",
    "https://www.dw.com/en/top-stories/s-9097/rss",

    # ── Nonprofit, philanthropy & NGO sector ──────────────────────────────────
    "https://nonprofitquarterly.org/feed/",
    "https://www.philanthropy.com/feed",
    "https://www.insidephilanthropy.com/home?format=rss",
    "https://www.thenewhumanitarian.org/rss.xml",            # Humanitarian affairs
    "https://www.devex.com/news/rss",                        # Int'l development
    "https://www.bond.org.uk/feed",                          # UK NGO sector
    "https://www.alliancemagazine.org/feed/",                # Global philanthropy
    "https://ssir.org/feed",                                  # Stanford Social Innovation Review

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
        content = resp.content
        print(f"  HTTP {resp.status_code}, {len(content)} bytes")
        if len(content) < 100:
            print(f"  [Tiny response] {content[:200]}")
            return []
        # Replace common HTML entities that break strict XML parsing
        for bad, good in [
            (b"&nbsp;", b" "), (b"&mdash;", b"&#8212;"), (b"&ndash;", b"&#8211;"),
            (b"&lsquo;", b"&#8216;"), (b"&rsquo;", b"&#8217;"), (b"&ldquo;", b"&#8220;"),
            (b"&rdquo;", b"&#8221;"), (b"&hellip;", b"&#8230;"), (b"&amp;amp;", b"&amp;"),
        ]:
            content = content.replace(bad, good)
        root = ET.fromstring(content)
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
