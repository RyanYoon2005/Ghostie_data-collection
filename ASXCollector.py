"""
ASXCollector.py — Fetch official ASX announcements for listed Australian companies.

Strategy:
  1. Use Finnhub symbol search to find candidate ticker symbols for the business.
  2. For each candidate, strip any exchange suffix (e.g. "ORG.AX" → "ORG") and
     verify it exists on ASX by calling the public ASX announcements API.
  3. If a valid ASX ticker is confirmed, fetch the latest announcements and
     normalise them into the standard Ghostie item format.

Returns [] silently for companies that are not ASX-listed, or when APIs are
unavailable — the collect pipeline should never fail because of this module.
"""

import os
from datetime import datetime

import requests

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
_FINNHUB_SEARCH_URL = "https://finnhub.io/api/v1/search"
_ASX_ANNOUNCEMENTS_URL = "https://www.asx.com.au/asx/1/company/{ticker}/announcements"
_ASX_BASE_URL = "https://www.asx.com.au"

# Headers required by the ASX public API — without a User-Agent it returns 403.
_ASX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.asx.com.au/",
}


def _find_asx_ticker(business_name: str) -> str | None:
    """
    Resolve a business name to its ASX ticker code.

    Uses Finnhub symbol search to get candidate tickers, then verifies each
    against the live ASX announcements API. Returns the first ticker that the
    ASX API confirms as valid, or None if the company is not ASX-listed.

    Args:
        business_name: Plain-English company name (e.g. "Origin Energy")

    Returns:
        ASX ticker string (e.g. "ORG"), or None.
    """
    if not FINNHUB_API_KEY:
        print("  FINNHUB_API_KEY not set — skipping ASX ticker resolution")
        return None

    # Step 1 — get candidates from Finnhub
    try:
        resp = requests.get(
            _FINNHUB_SEARCH_URL,
            params={"q": business_name, "token": FINNHUB_API_KEY},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  Finnhub search returned {resp.status_code} — skipping ASX lookup")
            return None
        candidates = resp.json().get("result", [])
    except Exception as exc:
        print(f"  Finnhub search error: {exc} — skipping ASX lookup")
        return None

    if not candidates:
        return None

    # Step 2 — verify each candidate against the ASX API (try up to 5)
    for entry in candidates[:5]:
        raw_symbol = entry.get("displaySymbol") or entry.get("symbol", "")
        # Strip exchange suffix: "ORG.AX" → "ORG", "CBA" → "CBA"
        asx_code = raw_symbol.split(".")[0].upper().strip()

        # ASX codes are 1–6 uppercase alpha characters (occasionally include digits)
        if not asx_code or len(asx_code) > 6 or not asx_code.replace("0", "").isalpha():
            continue

        try:
            verify = requests.get(
                _ASX_ANNOUNCEMENTS_URL.format(ticker=asx_code),
                params={"count": 1},
                headers=_ASX_HEADERS,
                timeout=8,
            )
            if verify.status_code == 200 and verify.json().get("data"):
                print(f"  Confirmed ASX ticker: {asx_code}")
                return asx_code
        except Exception:
            continue  # Try next candidate

    return None


def collect_asx_announcements(
    business_name: str,
    location: str,
    category: str,
    count: int = 20,
) -> list:
    """
    Fetch recent ASX announcements for a publicly listed Australian company.

    Args:
        business_name: Company name (e.g. "Origin Energy")
        location:      Location string (passed through to query metadata)
        category:      Category string (passed through to query metadata)
        count:         Number of announcements to fetch (default 20)

    Returns:
        List of standardised item dicts, or [] if the company is not ASX-listed
        or the API is unavailable.
    """
    print(f"  Resolving ASX ticker for '{business_name}'...")
    ticker = _find_asx_ticker(business_name)

    if not ticker:
        print(f"  '{business_name}' is not ASX-listed or ticker could not be resolved")
        return []

    try:
        resp = requests.get(
            _ASX_ANNOUNCEMENTS_URL.format(ticker=ticker),
            params={"count": count},
            headers=_ASX_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  ASX API returned {resp.status_code} for ticker {ticker}")
            return []
        announcements = resp.json().get("data", [])
    except Exception as exc:
        print(f"  ASX API error for {ticker}: {exc}")
        return []

    if not announcements:
        print(f"  No ASX announcements found for {ticker}")
        return []

    print(f"  Got {len(announcements)} ASX announcements for {ticker}")

    items = []
    for ann in announcements:
        ann_id = ann.get("id", "")
        # Build a stable unique ID
        item_id = (
            f"asx_{ticker}_{ann_id}"
            if ann_id
            else f"asx_{ticker}_{abs(hash(ann.get('header', '') + ann.get('document_date', '')))}"
        )

        # Build the full announcement URL
        url = ann.get("url", "")
        if not url:
            relative = ann.get("relative_url", "")
            url = f"{_ASX_BASE_URL}{relative}" if relative else ""

        # Prefer document_release_date (full ISO-8601) over document_date (date only)
        timestamp = ann.get("document_release_date") or ann.get("document_date") or datetime.utcnow().isoformat()

        title = ann.get("header", "")

        items.append({
            "id": item_id,
            "source": "asx_announcements",
            "publisher": f"ASX ({ticker})",
            "timestamp": timestamp,
            "query": {
                "business_name": business_name,
                "location": location,
                "category": category,
            },
            # Body mirrors title — the full filing is a PDF and cannot be scraped.
            # The announcement header is still rich enough for sentiment signals
            # (e.g. "Profit Warning", "Record Revenue", "CEO Resignation").
            "title": title,
            "body": title,
            "url": url,
            "data_type": "news_article",
            "metadata": {
                "ticker": ticker,
                "market_sensitive": ann.get("market_sensitive", False),
                "document_date": ann.get("document_date", ""),
                "number_of_pages": ann.get("number_of_pages"),
                "size": ann.get("size", ""),
            },
        })

    return items
