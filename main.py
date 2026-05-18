from fastapi import FastAPI, HTTPException
from mangum import Mangum
from pydantic import BaseModel
from datetime import datetime
import json
import logging
import os
import re

import requests as http_requests

# Import our collectors
from NewsCollector import collect_news, collect_news_reviews
from ReviewCollector import collect_reviews
from RedditCollector import collect_reddit_posts
from StockCollector import _search_symbol, _fetch_quote, collect_stock_history
from GoogleNewsRSSCollector import collect_google_news
from ASXCollector import collect_asx_announcements

# ── Local storage folder ─────────────────────────────────────────────────────
# Results are saved here until S3 is ready.
# When S3 is set up, swap this section for a boto3 upload — everything else stays the same.
# Lambda's filesystem is read-only except /tmp; use /tmp when running on Lambda
RESULTS_DIR = "/tmp/collected_data" if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else "collected_data"
os.makedirs(RESULTS_DIR, exist_ok=True)


def save_locally(data: dict) -> str:
    """
    Save collected results to a local JSON file.
    Filename format: collected_data/{business}_{location}_{timestamp}.json
    Returns the filepath so it can be logged or returned in the response.
    """
    # Sanitize business name and location for use in filename
    safe_name     = re.sub(r"[^a-zA-Z0-9]", "_", data["business_name"]).lower()
    safe_location = re.sub(r"[^a-zA-Z0-9]", "_", data["location"]).lower()
    timestamp     = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename      = f"{safe_name}_{safe_location}_{timestamp}.json"
    filepath      = os.path.join(RESULTS_DIR, filename)

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    return filepath


RETRIEVAL_API_BASE = os.environ["RETRIEVAL_API_BASE"]
RETRIEVAL_API_URL  = f"{RETRIEVAL_API_BASE}/store"


def post_to_retrieval_api(payload: dict) -> None:
    """
    POST collected data to the Retrieval API's /store endpoint.
    Logs a warning on failure but never raises — local file saving is unaffected.
    """
    body = {
        "business_name": payload["business_name"],
        "location":      payload["location"],
        "category":      payload["category"],
        "collected_at":  payload["collected_at"],
        "news_count":    payload["news_count"],
        "review_count":  payload["review_count"],
        "data":          payload["data"],
    }

    print(f"  [store] Posting to Retrieval API: {RETRIEVAL_API_URL}")
    print(f"  [store] Payload summary: business={payload['business_name']!r}, "
          f"location={payload['location']!r}, items={len(payload['data'])}")

    try:
        response = http_requests.post(RETRIEVAL_API_URL, json=body, timeout=25)
        print(f"  [store] Retrieval API responded: {response.status_code}")
        if response.status_code < 200 or response.status_code >= 300:
            logging.warning(
                "Retrieval API /store returned %s: %s",
                response.status_code,
                response.text[:200],
            )
            print(f"  [store] ERROR body: {response.text[:300]}")
        else:
            print(f"  [store] Successfully stored {len(payload['data'])} items")
    except Exception as exc:
        logging.warning("Failed to POST to Retrieval API: %s", exc)
        print(f"  [store] EXCEPTION posting to Retrieval API: {type(exc).__name__}: {exc}")


# ── App ──────────────────────────────────────────────────────────────────────

# When deployed on AWS Lambda behind API Gateway, the stage name (/Prod) is
# prepended to every path. FastAPI must know this so Swagger UI requests
# /Prod/openapi.json instead of /openapi.json (which API Gateway blocks with 403).
_root_path = "/Prod" if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else ""

app = FastAPI(
    title="Ghostie Data Collection API",
    description="Collects news articles and customer reviews for hospitality businesses to support sentiment analysis.",
    version="1.0.0",
    root_path=_root_path
)


# ── Request / Response Models ────────────────────────────────────────────────

class CollectRequest(BaseModel):
    business_name: str
    location: str
    category: str

    class Config:
        json_schema_extra = {
            "example": {
                "business_name": "Subway",
                "location": "Sydney",
                "category": "restaurant"
            }
        }

class CollectResponse(BaseModel):
    business_name: str
    location: str
    category: str
    collected_at: str
    total_results: int
    news_count: int
    news_review_count: int
    review_count: int
    reddit_count: int
    google_news_count: int
    asx_count: int
    score_only_count: int
    saved_to: str        # local filepath (will become S3 key later)
    data: list


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "Ghostie Data Collection API",
        "version": "1.0.0",
        "status":  "running",
        "endpoints": {
            "POST /collect":  "Collect news and reviews for a business",
            "GET /stock":     "Fetch stock quote + price history for a publicly listed business",
            "GET /health":    "Health check",
            "GET /results":   "List all saved result files"
        }
    }


@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/results")
def list_results():
    """List all locally saved result files."""
    files = os.listdir(RESULTS_DIR)
    files = [f for f in files if f.endswith(".json")]
    files.sort(reverse=True)  # most recent first
    return {
        "count": len(files),
        "files": files
    }


@app.get("/stock")
def stock(business_name: str, days_back: int = 365):
    """
    Return stock quote + daily price history for a publicly listed business.

    Intended for the frontend to render a sentiment-vs-stock-price correlation
    chart. Not part of the sentiment collection pipeline — called independently.

    Args:
        business_name : Company name to look up (e.g. "McDonald's")
        days_back     : Days of price history to return (default 365, max 365)

    Returns 404 if the business cannot be matched to a listed ticker.
    """
    business_name = business_name.strip()
    if not business_name:
        raise HTTPException(status_code=400, detail="business_name cannot be empty")

    symbol = _search_symbol(business_name)
    if not symbol:
        raise HTTPException(
            status_code=404,
            detail=f"No stock ticker found for '{business_name}'. It may not be publicly listed."
        )

    quote = _fetch_quote(symbol)

    # Validate that the matched symbol actually has live market data.
    # Finnhub's search can return obscure foreign exchange listings for
    # private companies (e.g. Subway → 511024.BO). If the quote has no
    # current price the symbol is useless — treat it as not found.
    if not quote or not quote.get("c"):
        raise HTTPException(
            status_code=404,
            detail=f"'{business_name}' does not appear to be publicly listed (no market data for symbol '{symbol}')."
        )

    candles = collect_stock_history(symbol, days_back=days_back)

    change_pct = None
    if quote.get("c") and quote.get("pc"):
        change_pct = round(((quote["c"] - quote["pc"]) / quote["pc"]) * 100, 2)

    return {
        "business_name": business_name,
        "symbol":        symbol,
        "quote": {
            "current_price":  quote.get("c") if quote else None,
            "open":           quote.get("o") if quote else None,
            "high":           quote.get("h") if quote else None,
            "low":            quote.get("l") if quote else None,
            "prev_close":     quote.get("pc") if quote else None,
            "change_percent": change_pct,
        },
        "history_days":  len(candles),
        "price_history": candles,   # [{date, open, high, low, close, volume}, ...]
    }


@app.post("/collect", response_model=CollectResponse)
def collect(request: CollectRequest):
    """
    Collect news articles and customer reviews for a hospitality business.

    - Calls NewsAPI to get recent news articles mentioning the business
    - Calls NewsAPI again with "review" in the query to get critic/publication reviews
    - Calls SerpAPI Google Maps Reviews to get real customer reviews with star ratings
      (reviews with no text body are tagged data_type="score_only")
    - Saves combined results to a local JSON file (will be S3 once infrastructure is ready)
    - Returns combined results in a standardized format for downstream processing
    """

    business_name = request.business_name.strip()
    location      = request.location.strip()
    category      = request.category.strip()

    if not business_name:
        raise HTTPException(status_code=400, detail="business_name cannot be empty")
    if not location:
        raise HTTPException(status_code=400, detail="location cannot be empty")
    if not category:
        raise HTTPException(status_code=400, detail="category cannot be empty")

    print(f"\n[{datetime.utcnow().isoformat()}] Collect request: {business_name} | {location} | {category}")

    # ── Collect from all sources ─────────────────────────────────────────────
    news_results         = []
    news_review_results  = []
    review_results       = []
    reddit_results       = []
    google_news_results  = []
    asx_results          = []
    errors               = []

    try:
        print("  Fetching news articles...")
        news_results = collect_news(business_name, location, category)
        print(f"  Got {len(news_results)} news articles")
    except Exception as e:
        errors.append(f"NewsAPI error: {str(e)}")
        print(f"  NewsAPI failed: {e}")

    try:
        print("  Fetching news reviews (critic/publication reviews)...")
        news_review_results = collect_news_reviews(business_name, location, category)
        print(f"  Got {len(news_review_results)} news reviews")
    except Exception as e:
        errors.append(f"NewsAPI reviews error: {str(e)}")
        print(f"  NewsAPI reviews failed: {e}")

    try:
        print("  Fetching Google Maps reviews...")
        review_results = collect_reviews(business_name, location, category)
        print(f"  Got {len(review_results)} reviews")
    except Exception as e:
        errors.append(f"SerpAPI error: {str(e)}")
        print(f"  SerpAPI failed: {e}")

    try:
        print("  Fetching Reddit posts...")
        reddit_results = collect_reddit_posts(business_name, location, category)
        print(f"  Got {len(reddit_results)} Reddit posts")
    except Exception as e:
        errors.append(f"Charlie API error: {str(e)}")
        print(f"  Charlie API failed: {e}")

    try:
        print("  Fetching Google News RSS...")
        google_news_results = collect_google_news(business_name, location, category)
        print(f"  Got {len(google_news_results)} Google News articles")
    except Exception as e:
        errors.append(f"Google News RSS error: {str(e)}")
        print(f"  Google News RSS failed: {e}")

    try:
        print("  Fetching ASX announcements...")
        asx_results = collect_asx_announcements(business_name, location, category)
        print(f"  Got {len(asx_results)} ASX announcements")
    except Exception as e:
        errors.append(f"ASX announcements error: {str(e)}")
        print(f"  ASX announcements failed: {e}")

    # ── Combine results ──────────────────────────────────────────────────────
    combined = news_results + news_review_results + review_results + reddit_results + google_news_results + asx_results

    if not combined:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for '{business_name}' in '{location}'. Errors: {errors}"
        )

    score_only_count = sum(1 for r in review_results if r.get("data_type") == "score_only")

    # ── Build response payload ───────────────────────────────────────────────
    payload = {
        "business_name":    business_name,
        "location":         location,
        "category":         category,
        "collected_at":     datetime.utcnow().isoformat(),
        "total_results":    len(combined),
        "news_count":       len(news_results),
        "news_review_count": len(news_review_results),
        "review_count":     len(review_results),
        "reddit_count":      len(reddit_results),
        "google_news_count": len(google_news_results),
        "asx_count":         len(asx_results),
        "score_only_count":  score_only_count,
        "data":             combined,
    }

    # ── Save locally ─────────────────────────────────────────────────────────
    # TODO: replace save_locally() with S3 upload when Do In Kim sets up the bucket
    filepath = save_locally(payload)
    print(f"  Saved to: {filepath}")

    payload["saved_to"] = filepath

    # ── POST to Retrieval API ────────────────────────────────────────────────
    post_to_retrieval_api(payload)

    return payload


@app.post("/refresh")
def refresh():
    """
    Re-collect data for every company already stored in DynamoDB.

    - Fetches the list of known companies from the Retrieval API's GET /companies
    - Re-runs /collect for each one and stores fresh results
    - Skips companies that were already collected within the last 24 hours
    - Returns a per-company summary (collected / skipped / failed)
    """
    # ── Fetch known companies ────────────────────────────────────────────────
    try:
        resp = http_requests.get(f"{RETRIEVAL_API_BASE}/companies", timeout=10)
        resp.raise_for_status()
        companies = resp.json().get("companies", [])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Retrieval API /companies: {exc}")

    if not companies:
        return {"message": "No companies in database. Nothing to refresh.", "results": []}

    cutoff = datetime.utcnow().replace(microsecond=0)

    results = []
    for company in companies:
        business_name = company.get("business_name", "")
        location      = company.get("location", "")
        category      = company.get("category", "")
        updated_at    = company.get("updated_at", "")

        # Skip if collected within the last 24 hours
        if updated_at:
            try:
                last_update = datetime.fromisoformat(updated_at)
                if (cutoff - last_update).total_seconds() < 86400:
                    results.append({
                        "business_name": business_name,
                        "location":      location,
                        "category":      category,
                        "status":        "skipped",
                        "reason":        "collected within last 24 hours",
                    })
                    continue
            except ValueError:
                pass  # unparseable date — proceed with refresh

        # Re-use existing collect logic directly
        try:
            result = collect(CollectRequest(
                business_name=business_name,
                location=location,
                category=category,
            ))
            results.append({
                "business_name": business_name,
                "location":      location,
                "category":      category,
                "status":        "collected",
                "total_results": result["total_results"],
            })
        except HTTPException as exc:
            results.append({
                "business_name": business_name,
                "location":      location,
                "category":      category,
                "status":        "failed",
                "reason":        exc.detail,
            })
        except Exception as exc:
            results.append({
                "business_name": business_name,
                "location":      location,
                "category":      category,
                "status":        "failed",
                "reason":        str(exc),
            })

    collected = sum(1 for r in results if r["status"] == "collected")
    skipped   = sum(1 for r in results if r["status"] == "skipped")
    failed    = sum(1 for r in results if r["status"] == "failed")

    return {
        "total":     len(companies),
        "collected": collected,
        "skipped":   skipped,
        "failed":    failed,
        "results":   results,
    }


# ── Lambda handler (Mangum wraps FastAPI for AWS Lambda) ─────────────────────
fastapi_handler = Mangum(app)

#events handler
def handler(event, context):
    """
    Master AWS Lambda Handler. Routes traffic based on who triggered it.
    """
    # 1. Check if EventBridge woke up the Lambda for the daily run
    if event.get("source") == "aws.events":
        print("EventBridge triggered! Running daily refresh bypassing FastAPI...")
        
        # Call your FastAPI endpoint function directly as a standard Python function
        result = refresh()
        
        print(f"Daily refresh complete: {result}")
        return {
            "statusCode": 200, 
            "body": json.dumps(result)
        }
    
    # 2. If it is NOT EventBridge, pass it to FastAPI as a normal web request
    return fastapi_handler(event, context)


# ── Run locally ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
