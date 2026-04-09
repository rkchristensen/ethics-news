"""
Generates index.html (current stories) and archive/YYYY-MM.html pages
from the JSON data files. Run this after fetch_and_classify.py, or
any time you want to rebuild the site without fetching new articles.
"""

import json
from pathlib import Path
from datetime import datetime
from html import escape

DATA_FILE       = Path("data/articles.json")
ARCHIVE_DATA    = Path("data/archive")
ARCHIVE_HTML    = Path("archive")
OUTPUT_INDEX    = Path("index.html")


# ── Data loaders ──────────────────────────────────────────────────────────────
def load_articles() -> list[dict]:
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f).get("articles", [])
    return []

def load_archive_months() -> list[dict]:
    months = []
    if ARCHIVE_DATA.exists():
        for f in sorted(ARCHIVE_DATA.glob("*.json"), reverse=True):
            try:
                dt = datetime.strptime(f.stem, "%Y-%m")
                months.append({
                    "key":   f.stem,
                    "label": dt.strftime("%B %Y"),
                    "file":  f,
                })
            except ValueError:
                pass
    return months


# ── HTML building blocks ───────────────────────────────────────────────────────
def tile_html(article: dict) -> str:
    tone        = article.get("tone", "neutral")
    border      = "tile-negative" if tone == "negative" else ("tile-positive" if tone == "positive" else "tile-neutral")
    us_attr     = "true" if article.get("us_story") else "false"
    title_esc   = escape(article.get("title", ""))
    url_esc     = escape(article.get("url", "#"))
    source      = escape(article.get("source", ""))
    date        = escape(article.get("date", ""))
    summary     = escape(article.get("summary", ""))
    search_text = escape((article.get("title", "") + " " + article.get("summary", "")).lower())

    summary_html = f'  <p class="tile-summary">{summary}</p>\n' if summary else ""

    return (
        f'<div class="tile {border}" data-us="{us_attr}" data-searchtext="{search_text}">\n'
        f'  <a href="{url_esc}" target="_blank" rel="noopener noreferrer" class="tile-title">{title_esc}</a>\n'
        f'{summary_html}'
        f'  <div class="tile-meta">{source} &bull; {date}</div>\n'
        f'</div>'
    )

def archive_nav(months: list[dict]) -> str:
    if not months:
        return ""
    links = " &nbsp;|&nbsp; ".join(
        f'<a href="archive/{m["key"]}.html">{m["label"]}</a>' for m in months
    )
    return f'<nav class="archive-nav"><strong>Archives:</strong> {links}</nav>'

def search_bar() -> str:
    return """<div class="search-bar">
  <input type="text" id="search-input" placeholder="&#128269; Search titles and summaries..." autocomplete="off" spellcheck="false">
</div>"""

def filter_bar() -> str:
    return """<div class="filter-bar">
  <span class="filter-label">Show:</span>
  <button class="filter-btn active" data-filter="all">All Stories</button>
  <button class="filter-btn" data-filter="us">US Only</button>
  <button class="filter-btn" data-filter="intl">International Only</button>
</div>"""

def legend() -> str:
    return """<div class="legend">
  <span class="legend-item negative">&#9632; Unethical / Misconduct</span>
  <span class="legend-item positive">&#9632; Positive / Accountability</span>
</div>"""


# ── Full page template ─────────────────────────────────────────────────────────
def build_page(
    articles:     list[dict],
    page_title:   str,
    nav_html:     str  = "",
    css_path:     str  = "assets/style.css",
    js_path:      str  = "assets/script.js",
    is_archive:   bool = False,
) -> str:
    sorted_articles = sorted(articles, key=lambda a: a.get("date", ""), reverse=True)
    gov = [a for a in sorted_articles if a.get("sector") in ("government", "both")]
    ngo = [a for a in sorted_articles if a.get("sector") in ("nonprofit", "both")]

    gov_tiles = "\n".join(tile_html(a) for a in gov) or '<p class="empty-msg">No stories yet.</p>'
    ngo_tiles = "\n".join(tile_html(a) for a in ngo) or '<p class="empty-msg">No stories yet.</p>'

    back_link = '<p class="back-link"><a href="../index.html">&larr; Back to current stories</a></p>' if is_archive else ""
    today     = datetime.now().strftime("%B %d, %Y")
    gov_count = len(gov)
    ngo_count = len(ngo)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(page_title)}</title>
  <link rel="stylesheet" href="{css_path}">
</head>
<body>
  <header>
    <h1>Ethics in the News</h1>
    <p class="subtitle">Tracking accountability in government &amp; nonprofits worldwide</p>
    <p class="updated">Updated {today}</p>
  </header>

  <main>
    {nav_html}
    {back_link}
    {search_bar()}
    {filter_bar()}
    {legend()}

    <div class="columns">
      <section class="column" id="gov-column">
        <h2>Government &amp; Public Sector <span class="count">({gov_count})</span></h2>
        <div class="tiles" id="gov-tiles">
          {gov_tiles}
        </div>
      </section>

      <section class="column" id="ngo-column">
        <h2>Nonprofits &amp; NGOs <span class="count">({ngo_count})</span></h2>
        <div class="tiles" id="ngo-tiles">
          {ngo_tiles}
        </div>
      </section>
    </div>
  </main>

  <footer>
    <p>
      Stories sourced automatically from global English-language news via
      <a href="https://news.google.com" target="_blank" rel="noopener">Google News</a>.
      Classified by keyword matching &mdash; always verify before sharing.
    </p>
  </footer>

  <script src="{js_path}"></script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=== Generate HTML ===")

    articles       = load_articles()
    archive_months = load_archive_months()

    # Main page
    nav_html = archive_nav(archive_months)
    html = build_page(articles, "Ethics in the News", nav_html=nav_html)
    OUTPUT_INDEX.write_text(html, encoding="utf-8")
    print(f"  Written: index.html  ({len(articles)} articles)")

    # Archive pages
    ARCHIVE_HTML.mkdir(exist_ok=True)
    for month in archive_months:
        with open(month["file"]) as f:
            arch_articles = json.load(f).get("articles", [])

        html = build_page(
            arch_articles,
            f"Ethics in the News — {month['label']}",
            css_path  = "../assets/style.css",
            js_path   = "../assets/script.js",
            is_archive= True,
        )
        out = ARCHIVE_HTML / f"{month['key']}.html"
        out.write_text(html, encoding="utf-8")
        print(f"  Written: archive/{month['key']}.html  ({len(arch_articles)} articles)")

    print("Done.")


if __name__ == "__main__":
    main()
