import requests
import json
import argparse
import os

CHARLIE_API_URL = os.environ.get("CHARLIE_API_URL", "")
CHARLIE_API_EMAIL = os.environ.get("CHARLIE_API_EMAIL", "")
CHARLIE_API_PASSWORD = os.environ.get("CHARLIE_API_PASSWORD", "")


def _get_charlie_token() -> str:
    """Authenticate with Charlie API and return a JWT token."""
    response = requests.post(
        f"{CHARLIE_API_URL}/v1/auth/login",
        json={"email": CHARLIE_API_EMAIL, "password": CHARLIE_API_PASSWORD},
        timeout=10,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Charlie auth failed: {response.status_code} {response.text[:200]}")
    return response.json()["token"]


def collect_reddit_posts(business_name: str, location: str, category: str, limit: int = 10) -> list:
    """
    Collect Reddit posts mentioning a specific business via Charlie's API.

    Args:
        business_name : Name of the business (e.g. "Subway")
        location      : City / region / country (e.g. "Sydney")
        category      : Type of business (e.g. "restaurant", "hotel", "bar")
        limit         : Max number of posts to return

    Returns:
        List of standardized post dicts, or [] on failure
    """
    if not CHARLIE_API_URL or not CHARLIE_API_EMAIL or not CHARLIE_API_PASSWORD:
        print("  Charlie API credentials not configured — skipping Reddit collection")
        return []

    print(f"\n Searching Reddit for: '{business_name}'")
    print(f"   Location : {location}")
    print(f"   Category : {category}\n")

    try:
        token = _get_charlie_token()
    except Exception as e:
        print(f"  Charlie auth error: {e}")
        return []

    headers = {"Authorization": f"Bearer {token}"}
    query = f"{business_name} {category}"

    response = requests.get(
        f"{CHARLIE_API_URL}/v1/post/search",
        params={"query": query, "limit": limit},
        headers=headers,
        timeout=30,
    )

    if response.status_code != 200:
        print(f"  Charlie API error {response.status_code}: {response.text[:200]}")
        return []

    data = response.json()
    raw_posts = data.get("data", {}).get("events", [])
    print(f"  Fetched {len(raw_posts)} Reddit posts\n")

    if not raw_posts:
        print("  No Reddit posts found.")
        return []

    standardized = []
    for event in raw_posts:
        attrs = event.get("attributes", {})
        time_obj = event.get("time_object", {})
        standardized.append({
            "id":        f"reddit_{abs(hash(attrs.get('id', attrs.get('title', ''))))}",
            "source":    "reddit",
            "publisher": f"r/{attrs.get('subreddit', 'unknown')}",
            "timestamp": time_obj.get("timestamp", ""),
            "query": {
                "business_name": business_name,
                "location":      location,
                "category":      category,
            },
            "title": attrs.get("title", ""),
            "body":  attrs.get("selftext", ""),
            "url":   f"https://www.reddit.com/r/{attrs.get('subreddit', '')}/comments/{attrs.get('id', '')}",
            "data_type": "text_review" if attrs.get("selftext") else "title_only",
            "metadata": {
                "author":    attrs.get("author", ""),
                "score":     attrs.get("score", 0),
                "subreddit": attrs.get("subreddit", ""),
            },
        })

    return standardized


# ── CLI entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Reddit posts for a hospitality business via Charlie API.")
    parser.add_argument("business",   nargs="?", help='Business name e.g. "Subway"')
    parser.add_argument("--location", help="City / region / country")
    parser.add_argument("--category", help="Business type e.g. restaurant, hotel, bar")
    parser.add_argument("--limit",    type=int, default=10, help="Max posts to fetch (default 10)")
    parser.add_argument("--out",      default="reddit_results.json")
    args = parser.parse_args()

    business_name = (args.business  or "").strip() or input("Enter business name: ").strip()
    location      = (args.location  or "").strip() or input("Enter location: ").strip()
    category      = (args.category  or "").strip() or input("Enter category: ").strip()

    if not business_name:
        raise SystemExit("  Business name cannot be empty.")
    if not location:
        raise SystemExit("  Location cannot be empty.")
    if not category:
        raise SystemExit("  Category cannot be empty.")

    results = collect_reddit_posts(business_name, location, category, limit=args.limit)

    for i, post in enumerate(results, 1):
        print(f"Post {i}:")
        print(f"  Subreddit : {post['metadata']['subreddit']}")
        print(f"  Title     : {post['title']}")
        print(f"  Author    : {post['metadata']['author']}")
        print(f"  Score     : {post['metadata']['score']}")
        print(f"  Date      : {post['timestamp']}")
        body_preview = post['body'][:150] + "..." if len(post['body']) > 150 else post['body']
        print(f"  Body      : {body_preview if body_preview else 'No text'}")
        print(f"  URL       : {post['url']}")
        print()

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  {len(results)} posts saved to {args.out}")
