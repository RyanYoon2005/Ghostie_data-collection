import requests
import json
import argparse
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

GNEWS_RSS_URL = "https://news.google.com/rss/search"


def collect_google_news(business_name: str, location: str, category: str, max_results: int = 20):
    """
    Collect Google News articles for a business via Google News RSS feed.
    Completely free — no API key required.

    Args:
        business_name : Name of the business (e.g. "Subway")
        location      : City / region / country (e.g. "Sydney")
        category      : Type of business (e.g. "restaurant", "hotel", "bar")
        max_results   : Max number of articles to return (default 20)

    Returns:
        List of standardized article dicts
    """

    query = f'"{business_name}" {category} {location}'

    params = {
        "q":    query,
        "hl":   "en-AU",
        "gl":   "AU",
        "ceid": "AU:en",
    }

    print(f"\n Searching Google News RSS for: '{business_name}'")
    print(f"   Location : {location}")
    print(f"   Category : {category}")
    print(f"   Query    : {query}\n")

    headers = {"User-Agent": "Mozilla/5.0 (compatible; GhostieBot/1.0)"}
    response = requests.get(GNEWS_RSS_URL, params=params, headers=headers, timeout=30)

    if response.status_code != 200:
        print(f"  Google News RSS error {response.status_code}")
        return []

    # ── Parse RSS XML ──
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        print(f"  Failed to parse RSS XML: {e}")
        return []

    channel = root.find("channel")
    if channel is None:
        print("  No channel found in RSS feed.")
        return []

    items = channel.findall("item")
    print(f"  Google News RSS returned {len(items)} articles")

    if not items:
        print("  No articles returned.")
        return []

    # ── Standardize into our data model ──
    standardized = []
    for item in items[:max_results]:
        title   = item.findtext("title") or ""
        link    = item.findtext("link") or ""
        pub_date = item.findtext("pubDate") or ""
        source  = item.findtext("source") or ""
        description = item.findtext("description") or ""

        # Parse pubDate into ISO format
        timestamp = ""
        if pub_date:
            try:
                timestamp = parsedate_to_datetime(pub_date).astimezone(timezone.utc).isoformat()
            except Exception:
                timestamp = pub_date

        standardized.append({
            "id":        f"gnews_rss_{abs(hash(link or title))}",
            "source":    "google_news_rss",
            "publisher": source,
            "timestamp": timestamp,
            "query": {
                "business_name": business_name,
                "location":      location,
                "category":      category,
            },
            "title": title,
            "body":  description,
            "url":   link,
            "metadata": {
                "author": "",
            },
        })

    print(f"  Returning {len(standardized)} Google News articles\n")
    return standardized


# ── CLI entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Google News articles for a hospitality business via RSS.")
    parser.add_argument("business",   nargs="?", help='Business name e.g. "Subway"')
    parser.add_argument("--location", help="City / region / country")
    parser.add_argument("--category", help="Business type e.g. restaurant, hotel, bar")
    parser.add_argument("--max",      type=int, default=20, help="Max articles to return (default 20)")
    parser.add_argument("--out",      default="gnews_rss_results.json")
    args = parser.parse_args()

    business_name = (args.business  or "").strip() or input("Enter business name: ").strip()
    location      = (args.location  or "").strip() or input("Enter location (city / country): ").strip()
    category      = (args.category  or "").strip() or input("Enter category (restaurant / hotel / bar): ").strip()

    if not business_name:
        raise SystemExit("  Business name cannot be empty.")
    if not location:
        raise SystemExit("  Location cannot be empty.")
    if not category:
        raise SystemExit("  Category cannot be empty.")

    results = collect_google_news(business_name, location, category, max_results=args.max)

    for i, article in enumerate(results, 1):
        print(f"Article {i}:")
        print(f"  Publisher : {article['publisher']}")
        print(f"  Title     : {article['title']}")
        print(f"  Date      : {article['timestamp']}")
        body_preview = article['body'][:120] + "..." if len(article['body']) > 120 else article['body']
        print(f"  Summary   : {body_preview if body_preview else 'N/A'}")
        print(f"  URL       : {article['url']}")
        print()

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  {len(results)} articles saved to {args.out}")
