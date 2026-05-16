import requests
import json
import argparse
import os

SCRAPER_API_KEY  = os.environ["SCRAPER_API_KEY"]
SCRAPER_BASE_URL = "https://api.scraperapi.com/structured/google/news"


def collect_scraper_news(business_name: str, location: str, category: str):
    """
    Collect Google News articles for a business via ScraperAPI's structured Google News endpoint.

    Args:
        business_name : Name of the business (e.g. "Subway")
        location      : City / region / country (e.g. "Sydney")
        category      : Type of business (e.g. "restaurant", "hotel", "bar")

    Returns:
        List of standardized article dicts
    """

    query = f'"{business_name}" {category} {location}'

    params = {
        "api_key":      SCRAPER_API_KEY,
        "query":        query,
        "country_code": "us",
        "tld":          "com",
        "hl":           "en",
    }

    print(f"\n Searching Google News (ScraperAPI) for: '{business_name}'")
    print(f"   Location : {location}")
    print(f"   Category : {category}")
    print(f"   Query    : {query}\n")

    response = requests.get(SCRAPER_BASE_URL, params=params, timeout=30)

    if response.status_code != 200:
        print(f"  ScraperAPI error {response.status_code}: {response.text[:300]}")
        return []

    data        = response.json()
    raw_results = data.get("articles", [])

    print(f"  ScraperAPI returned {len(raw_results)} news results")

    if not raw_results:
        print("  No Google News results returned.")
        return []

    # No relevance filter here — the Google News query already uses a quoted
    # business name so results are targeted. Unlike NewsAPI (100 loose results),
    # we trust Google News to return on-topic articles.

    # ── Standardize into our data model ──
    standardized = []
    for article in raw_results:
        source_name = article.get("source", {}).get("name", "Unknown") if isinstance(article.get("source"), dict) else article.get("source", "Unknown")
        standardized.append({
            "id":        f"gnews_{abs(hash(article.get('link', article.get('title', ''))))}",
            "source":    "google_news",
            "publisher": source_name,
            "timestamp": article.get("date", ""),
            "query": {
                "business_name": business_name,
                "location":      location,
                "category":      category,
            },
            "title": article.get("title", ""),
            "body":  article.get("snippet", ""),
            "url":   article.get("link", ""),
            "metadata": {
                "author": "",
            },
        })

    return standardized


# ── CLI entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Google News articles for a hospitality business via ScraperAPI.")
    parser.add_argument("business",   nargs="?", help='Business name e.g. "Subway"')
    parser.add_argument("--location", help="City / region / country")
    parser.add_argument("--category", help="Business type e.g. restaurant, hotel, bar")
    parser.add_argument("--out",      default="scraper_news_results.json")
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

    results = collect_scraper_news(business_name, location, category)

    for i, article in enumerate(results, 1):
        print(f"Article {i}:")
        print(f"  Publisher : {article['publisher']}")
        print(f"  Title     : {article['title']}")
        print(f"  Date      : {article['timestamp']}")
        body_preview = article['body'][:120] + "..." if len(article['body']) > 120 else article['body']
        print(f"  Snippet   : {body_preview if body_preview else 'N/A'}")
        print(f"  URL       : {article['url']}")
        print()

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  {len(results)} articles saved to {args.out}")
