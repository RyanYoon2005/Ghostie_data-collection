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
import yfinance as yf

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
_FINNHUB_SEARCH_URL = "https://finnhub.io/api/v1/search"

# Primary: Markit Digital ASX API — works from cloud/Lambda environments
_MARKIT_ANNOUNCEMENTS_URL = "https://asx.api.markitdigital.com/asx-research/1.0/companies/announcements"
# Fallback: direct ASX website API
_ASX_ANNOUNCEMENTS_URL = "https://www.asx.com.au/asx/1/company/{ticker}/announcements"
_ASX_BASE_URL = "https://www.asx.com.au"

# Hardcoded map for major ASX companies where Finnhub search may be unreliable.
# Keys are lowercase business name substrings.
_KNOWN_ASX_TICKERS: dict[str, str] = {
    "commonwealth bank": "CBA",
    "westpac": "WBC",
    "national australia bank": "NAB",
    "anz bank": "ANZ",
    "anz": "ANZ",
    "bhp": "BHP",
    "rio tinto": "RIO",
    "woolworths": "WOW",
    "wesfarmers": "WES",
    "telstra": "TLS",
    "csl": "CSL",
    "macquarie": "MQG",
    "origin energy": "ORG",
    "qantas": "QAN",
    "fortescue": "FMG",
    "woodside": "WDS",
    "santos": "STO",
    "transurban": "TCL",
    "scentre": "SCG",
    "goodman": "GMG",
    "amp": "AMP",
    "suncorp": "SUN",
    "insurance australia": "IAG",
    "medibank": "MPL",
    "ramsay": "RHC",
    "cochlear": "COH",
    "resmed": "RMD",
    "james hardie": "JHX",
    "seek": "SEK",
    "car group": "CAR",
    "carsales": "CAR",
    "realestate": "REA",
    "rea group": "REA",
    "domain": "DHG",
    "afterpay": "APT",
    "zip": "ZIP",
    "nab": "NAB",
    "optiver": "OPT",
    "coles": "COL",
}

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


def _verify_asx_ticker(asx_code: str) -> bool:
    """Return True if the Markit or ASX API confirms this ticker has announcements."""
    # Try Markit Digital first (works from Lambda)
    try:
        resp = requests.get(
            _MARKIT_ANNOUNCEMENTS_URL,
            params={"companyCode": asx_code, "count": 1},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            return bool(data.get("data", {}).get("items") or data.get("items"))
    except Exception:
        pass
    # Fallback to direct ASX API
    try:
        resp = requests.get(
            _ASX_ANNOUNCEMENTS_URL.format(ticker=asx_code),
            params={"count": 1},
            headers=_ASX_HEADERS,
            timeout=8,
        )
        return resp.status_code == 200 and bool(resp.json().get("data"))
    except Exception:
        return False


def _find_asx_ticker(business_name: str) -> str | None:
    """
    Resolve a business name to its ASX ticker code.

    Strategy (in order):
    1. Check the hardcoded known-ticker map for major ASX companies.
    2. Use Finnhub symbol search (Australian exchange results preferred).
    3. Verify every candidate against the live ASX announcements API.

    Returns the first confirmed ticker, or None if not ASX-listed.
    """
    name_lower = business_name.lower().strip()

    # Step 1 — check hardcoded map (substring match so "Commonwealth Bank of Australia" → CBA)
    for key, ticker in _KNOWN_ASX_TICKERS.items():
        if key in name_lower or name_lower in key:
            print(f"  Matched known ASX ticker '{ticker}' for '{business_name}'")
            return ticker

    # Step 2 — Finnhub search (requires API key)
    if not FINNHUB_API_KEY:
        print("  FINNHUB_API_KEY not set — skipping Finnhub ASX search")
        return None

    # Try with exchange=AU filter first for more accurate Australian results
    candidates: list = []
    for params in [
        {"q": business_name, "exchange": "AU", "token": FINNHUB_API_KEY},
        {"q": business_name, "token": FINNHUB_API_KEY},
    ]:
        try:
            resp = requests.get(_FINNHUB_SEARCH_URL, params=params, timeout=10)
            if resp.status_code == 200:
                results = resp.json().get("result", [])
                # Prefer symbols with .AX suffix (ASX-listed)
                ax_results = [r for r in results if ".AX" in r.get("displaySymbol", "") or ".AX" in r.get("symbol", "")]
                candidates = ax_results if ax_results else results
                if candidates:
                    break
        except Exception as exc:
            print(f"  Finnhub search error: {exc}")
            continue

    # Step 3 — verify Finnhub candidates against the ASX API (try up to 5)
    for entry in candidates[:5]:
        raw_symbol = entry.get("displaySymbol") or entry.get("symbol", "")
        # Strip exchange suffix: "CBA.AX" → "CBA", "ORG" → "ORG"
        asx_code = raw_symbol.split(".")[0].upper().strip()

        # ASX codes: 1–6 chars, letters only (or letters + digits for some ETFs)
        if not asx_code or len(asx_code) > 6 or not asx_code.isalnum():
            continue

        if _verify_asx_ticker(asx_code):
            print(f"  Confirmed ASX ticker via Finnhub: {asx_code}")
            return asx_code

    # Step 4 — yfinance fallback: search using Yahoo Finance which natively supports .AX
    try:
        search = yf.Search(business_name, max_results=5)
        for quote in search.quotes:
            symbol = quote.get("symbol", "")
            if symbol.endswith(".AX"):
                asx_code = symbol[:-3]  # strip ".AX"
                if _verify_asx_ticker(asx_code):
                    print(f"  Confirmed ASX ticker via yfinance: {asx_code}")
                    return asx_code
    except Exception as exc:
        print(f"  yfinance search error: {exc}")

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

    announcements = []

    # Try Markit Digital API first (works from Lambda/cloud environments)
    try:
        resp = requests.get(
            _MARKIT_ANNOUNCEMENTS_URL,
            params={"companyCode": ticker, "count": count},
            timeout=10,
        )
        if resp.status_code == 200:
            body = resp.json()
            # Markit wraps items under data.items or items depending on version
            announcements = (
                body.get("data", {}).get("items")
                or body.get("items")
                or []
            )
            if announcements:
                print(f"  Fetched {len(announcements)} announcements via Markit API")
    except Exception as exc:
        print(f"  Markit API error for {ticker}: {exc}")

    # Fallback to direct ASX API if Markit returned nothing
    if not announcements:
        try:
            resp = requests.get(
                _ASX_ANNOUNCEMENTS_URL.format(ticker=ticker),
                params={"count": count},
                headers=_ASX_HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                announcements = resp.json().get("data", [])
            else:
                print(f"  ASX API returned {resp.status_code} for ticker {ticker}")
        except Exception as exc:
            print(f"  ASX API error for {ticker}: {exc}")

    if not announcements:
        print(f"  No ASX announcements found for {ticker}")
        return []

    print(f"  Got {len(announcements)} ASX announcements for {ticker}")

    items = []
    for ann in announcements:
        # Support both ASX API field names and Markit Digital field names
        ann_id = ann.get("id", "") or ann.get("id", "")
        title = ann.get("header") or ann.get("headline") or ann.get("title") or ""
        timestamp = (
            ann.get("document_release_date")
            or ann.get("dateTime")
            or ann.get("document_date")
            or datetime.utcnow().isoformat()
        )
        market_sensitive = ann.get("market_sensitive") or ann.get("isMarketSensitive") or False
        document_date = ann.get("document_date") or ann.get("dateTime", "")[:10] if ann.get("dateTime") else ""

        # Build a stable unique ID
        item_id = (
            f"asx_{ticker}_{ann_id}"
            if ann_id
            else f"asx_{ticker}_{abs(hash(title + document_date))}"
        )

        # Build the full announcement URL
        url = ann.get("url") or ann.get("pdfUrl") or ""
        if not url:
            relative = ann.get("relative_url", "")
            url = f"{_ASX_BASE_URL}{relative}" if relative else ""

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
            "title": title,
            "body": title,
            "url": url,
            "data_type": "news_article",
            "metadata": {
                "ticker": ticker,
                "market_sensitive": market_sensitive,
                "document_date": document_date,
                "number_of_pages": ann.get("number_of_pages") or ann.get("numberOfPages"),
                "size": ann.get("size", ""),
            },
        })

    return items
