import requests
import json
import argparse
import os
from datetime import datetime, timedelta
import yfinance as yf

API_KEY = os.environ.get("FINNHUB_API_KEY", "")
BASE_URL = "https://finnhub.io/api/v1"

MAX_DAYS_BACK = 30
MAX_CANDLE_DAYS = 365  # Finnhub free tier supports up to 1 year of daily candles


def _search_symbol(business_name: str) -> str | None:
    """
    Search Finnhub for a stock ticker matching the business name.
    Returns the best-match symbol, or None if not found.
    """
    response = requests.get(
        f"{BASE_URL}/search",
        params={"q": business_name, "token": API_KEY},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"  Finnhub symbol search error {response.status_code}: {response.text[:200]}")
        return None

    results = response.json().get("result", [])
    if not results:
        return None

    # Prefer an exact (case-insensitive) display name match, otherwise take top result
    name_lower = business_name.lower()
    for r in results:
        if r.get("description", "").lower() == name_lower:
            return r["symbol"]

    return results[0]["symbol"]


def _fetch_quote(symbol: str) -> dict | None:
    """Fetch the current stock quote for a symbol."""
    response = requests.get(
        f"{BASE_URL}/quote",
        params={"symbol": symbol, "token": API_KEY},
        timeout=10,
    )
    if response.status_code != 200:
        return None
    return response.json()


def _fetch_company_news(symbol: str, date_from: str, date_to: str) -> list:
    """Fetch recent company news from Finnhub for a given symbol."""
    response = requests.get(
        f"{BASE_URL}/company-news",
        params={"symbol": symbol, "from": date_from, "to": date_to, "token": API_KEY},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"  Finnhub news error {response.status_code}: {response.text[:200]}")
        return []
    return response.json() if isinstance(response.json(), list) else []


def collect_stock_history(symbol: str, days_back: int = MAX_CANDLE_DAYS) -> list:
    """
    Fetch daily OHLC candle data for a symbol via Yahoo Finance (yfinance).

    Uses yfinance instead of Finnhub's candle endpoint because Finnhub's free
    tier restricts historical daily candles. yfinance is free, requires no API
    key, and provides full OHLCV history.

    Args:
        symbol   : Stock ticker (e.g. "MCD")
        days_back: How many calendar days of history to fetch (max 365)

    Returns:
        List of dicts sorted oldest → newest:
        [{"date": "YYYY-MM-DD", "open": float, "high": float,
           "low": float, "close": float, "volume": int}, ...]
    """
    days_back = min(days_back, MAX_CANDLE_DAYS)
    date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_to   = datetime.now().strftime("%Y-%m-%d")

    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(start=date_from, end=date_to, interval="1d")

        if hist.empty:
            print(f"  yfinance: no candle data for {symbol}")
            return []

        candles = []
        for date, row in hist.iterrows():
            candles.append({
                "date":   date.strftime("%Y-%m-%d"),
                "open":   round(float(row["Open"]), 2),
                "high":   round(float(row["High"]), 2),
                "low":    round(float(row["Low"]), 2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return candles

    except Exception as e:
        print(f"  yfinance error for {symbol}: {e}")
        return []


def collect_stock_data(business_name: str, location: str, category: str, days_back: int = MAX_DAYS_BACK) -> list:
    """
    Collect stock price and company news for a publicly listed hospitality business.

    Strategy:
      1. Search Finnhub for the business's stock ticker symbol.
      2. If found, fetch the current quote and recent company news.
      3. Return a standardized list — one item per news article, plus one
         summary item containing the current stock price/movement.

    Args:
        business_name : Name of the business (e.g. "McDonald's")
        location      : City / region / country (e.g. "Australia")
        category      : Type of business (e.g. "restaurant", "hotel")
        days_back     : How many days back to fetch news (default 30)

    Returns:
        List of standardized dicts, or [] if the business is not listed / API fails.
    """
    if not API_KEY:
        print("  FINNHUB_API_KEY not configured — skipping stock collection")
        return []

    days_back = min(days_back, MAX_DAYS_BACK)
    date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_to   = datetime.now().strftime("%Y-%m-%d")

    print(f"\n Searching Finnhub stock data for: '{business_name}'")
    print(f"   Location : {location}")
    print(f"   Category : {category}")
    print(f"   Dates    : {date_from} to {date_to}\n")

    # Step 1 — find ticker
    symbol = _search_symbol(business_name)
    if not symbol:
        print(f"  No stock symbol found for '{business_name}' — likely not publicly listed")
        return []

    print(f"  Found symbol: {symbol}")

    # Step 2 — fetch quote and news in parallel-ish (sequential is fine at this scale)
    quote      = _fetch_quote(symbol)
    news_items = _fetch_company_news(symbol, date_from, date_to)
    print(f"  Fetched quote + {len(news_items)} company news articles\n")

    standardized = []

    # Stock price summary item
    if quote and quote.get("c"):  # 'c' = current price
        change_pct = round(((quote["c"] - quote["pc"]) / quote["pc"]) * 100, 2) if quote.get("pc") else None
        standardized.append({
            "id":        f"stock_quote_{symbol}_{date_to}",
            "source":    "finnhub_quote",
            "publisher": "Finnhub",
            "timestamp": datetime.utcnow().isoformat(),
            "query": {
                "business_name": business_name,
                "location":      location,
                "category":      category,
            },
            "title": f"{symbol} stock quote — {date_to}",
            "body":  (
                f"Current price: ${quote['c']} | "
                f"Open: ${quote.get('o')} | "
                f"High: ${quote.get('h')} | "
                f"Low: ${quote.get('l')} | "
                f"Prev close: ${quote.get('pc')} | "
                f"Change: {change_pct}%"
            ),
            "url": f"https://finance.yahoo.com/quote/{symbol}",
            "data_type": "stock_quote",
            "metadata": {
                "symbol":         symbol,
                "current_price":  quote.get("c"),
                "open":           quote.get("o"),
                "high":           quote.get("h"),
                "low":            quote.get("l"),
                "prev_close":     quote.get("pc"),
                "change_percent": change_pct,
            },
        })

    # Company news items
    for article in news_items:
        timestamp = datetime.utcfromtimestamp(article.get("datetime", 0)).isoformat() if article.get("datetime") else ""
        standardized.append({
            "id":        f"stock_news_{abs(hash(article.get('url', article.get('id', ''))))}",
            "source":    "finnhub_news",
            "publisher": article.get("source", "Unknown"),
            "timestamp": timestamp,
            "query": {
                "business_name": business_name,
                "location":      location,
                "category":      category,
            },
            "title": article.get("headline", ""),
            "body":  article.get("summary", ""),
            "url":   article.get("url", ""),
            "data_type": "news_article",
            "metadata": {
                "symbol":   symbol,
                "category": article.get("category", ""),
                "image":    article.get("image", ""),
            },
        })

    return standardized


# ── CLI entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect stock data for a hospitality business via Finnhub.")
    parser.add_argument("business",    nargs="?", help='Business name e.g. "McDonald\'s"')
    parser.add_argument("--location",  help="City / region / country")
    parser.add_argument("--category",  help="Business type e.g. restaurant, hotel, bar")
    parser.add_argument("--days-back", type=int, default=MAX_DAYS_BACK)
    parser.add_argument("--out",       default="stock_results.json")
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

    results = collect_stock_data(business_name, location, category, days_back=args.days_back)

    for i, item in enumerate(results, 1):
        print(f"Item {i}: [{item['source']}]")
        print(f"  Symbol    : {item['metadata'].get('symbol', 'N/A')}")
        print(f"  Title     : {item['title']}")
        print(f"  Date      : {item['timestamp']}")
        body_preview = item['body'][:150] + "..." if len(item['body']) > 150 else item['body']
        print(f"  Body      : {body_preview}")
        print(f"  URL       : {item['url']}")
        print()

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  {len(results)} items saved to {args.out}")
