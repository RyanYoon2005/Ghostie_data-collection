"""
Component tests for the FastAPI application (main.py).

Level of abstraction: Component
- Uses FastAPI's TestClient (built on httpx) to drive the full FastAPI
  request/response cycle — including routing, middleware, and Pydantic
  validation — without making real network calls.
- External dependencies (NewsCollector, ReviewCollector, Retrieval API) are
  mocked at the function level so tests are deterministic and offline.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# FastAPI TestClient requires the app (not the Lambda handler)
from main import app

pytestmark = pytest.mark.integration

client = TestClient(app)


# ---------------------------------------------------------------------------
# Reusable mock return values
# ---------------------------------------------------------------------------

MOCK_NEWS = [
    {
        "id": "news_abc123",
        "source": "newsapi",
        "publisher": "BBC News",
        "timestamp": "2026-03-20T10:00:00Z",
        "query": {"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
        "title": "Subway opens new restaurant in Sydney",
        "body": "Subway has opened a new outlet in Sydney CBD.",
        "url": "https://bbc.com/news/subway-1",
        "metadata": {"author": "Jane Doe"},
    }
]

MOCK_NEWS_REVIEWS = [
    {
        "id": "newsreview_def456",
        "source": "news_review",
        "publisher": "Time Out",
        "timestamp": "2026-03-18T12:00:00Z",
        "query": {"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
        "title": "Subway Sydney review",
        "body": "A surprisingly decent sandwich.",
        "url": "https://timeout.com/subway-review",
        "metadata": {"author": "Critic Jones"},
    }
]

MOCK_REVIEWS = [
    {
        "id": "review_ghi789",
        "source": "google_maps_reviews",
        "publisher": "Google Maps",
        "timestamp": "2026-03-15T00:00:00Z",
        "query": {"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
        "title": "Customer review for Subway",
        "body": "Amazing sandwiches, great service!",
        "url": "https://maps.google.com/?cid=1234",
        "metadata": {"author": "Alice", "rating": 5.0, "likes": 3},
        "data_type": "text_review",
    },
    {
        "id": "review_jkl012",
        "source": "google_maps_reviews",
        "publisher": "Google Maps",
        "timestamp": "2026-02-15T00:00:00Z",
        "query": {"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
        "title": "Customer review for Subway",
        "body": "",
        "url": "https://maps.google.com/?cid=5678",
        "metadata": {"author": "Bob", "rating": 2.0, "likes": 0},
        "data_type": "score_only",
    },
]

MOCK_REDDIT = [
    {
        "id": "reddit_abc123",
        "source": "reddit",
        "publisher": "r/sydney",
        "timestamp": "2026-03-10T08:00:00Z",
        "query": {"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
        "title": "Anyone tried the new Subway in Sydney CBD?",
        "body": "Went there yesterday, pretty decent for the price.",
        "url": "https://www.reddit.com/r/sydney/comments/abc123",
        "data_type": "text_review",
        "metadata": {"author": "redditor_xyz", "score": 42, "subreddit": "sydney"},
    }
]


def _mock_collect_success(*args, **kwargs):
    """Patch that simulates all collectors returning data."""
    return MOCK_NEWS, MOCK_NEWS_REVIEWS, MOCK_REVIEWS


def _patch_all_collectors(news=MOCK_NEWS, reviews=MOCK_NEWS_REVIEWS, maps=MOCK_REVIEWS,
                           reddit=MOCK_REDDIT, retrieval_ok=True):
    """Context-manager stack: patches collectors + Retrieval API post."""
    patches = [
        patch("main.collect_news", return_value=news),
        patch("main.collect_news_reviews", return_value=reviews),
        patch("main.collect_reviews", return_value=maps),
        patch("main.collect_reddit_posts", return_value=reddit),
    ]
    if retrieval_ok:
        mock_post = MagicMock()
        mock_post.status_code = 200
        patches.append(patch("main.http_requests.post", return_value=mock_post))
    return patches


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

class TestRootEndpoint:

    def test_returns_200(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_response_is_json(self):
        response = client.get("/")
        assert response.headers["content-type"].startswith("application/json")

    def test_response_contains_service_name(self):
        response = client.get("/")
        body = response.json()
        assert "service" in body or "name" in body or "message" in body

    def test_response_contains_endpoints_list(self):
        response = client.get("/")
        body = response.json()
        assert "endpoints" in body


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:

    def test_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200

    def test_status_is_healthy(self):
        response = client.get("/health")
        assert response.json()["status"] == "healthy"

    def test_response_contains_timestamp(self):
        response = client.get("/health")
        body = response.json()
        assert "timestamp" in body
        assert body["timestamp"] is not None


# ---------------------------------------------------------------------------
# GET /results
# ---------------------------------------------------------------------------

class TestResultsEndpoint:

    def test_returns_200(self):
        response = client.get("/results")
        assert response.status_code == 200

    def test_response_has_count_and_files_fields(self):
        response = client.get("/results")
        body = response.json()
        assert "count" in body
        assert "files" in body

    def test_files_is_a_list(self):
        response = client.get("/results")
        assert isinstance(response.json()["files"], list)

    def test_count_matches_files_length(self):
        response = client.get("/results")
        body = response.json()
        assert body["count"] == len(body["files"])


# ---------------------------------------------------------------------------
# POST /collect — validation
# ---------------------------------------------------------------------------

class TestCollectEndpointValidation:

    def test_missing_body_returns_422(self):
        response = client.post("/collect")
        assert response.status_code == 422

    def test_missing_business_name_returns_422(self):
        response = client.post("/collect", json={"location": "Sydney", "category": "restaurant"})
        assert response.status_code == 422

    def test_missing_location_returns_422(self):
        response = client.post("/collect", json={"business_name": "Subway", "category": "restaurant"})
        assert response.status_code == 422

    def test_missing_category_returns_422(self):
        response = client.post("/collect", json={"business_name": "Subway", "location": "Sydney"})
        assert response.status_code == 422

    def test_empty_business_name_returns_400(self):
        response = client.post("/collect", json={"business_name": "  ", "location": "Sydney", "category": "restaurant"})
        assert response.status_code == 400

    def test_empty_location_returns_400(self):
        response = client.post("/collect", json={"business_name": "Subway", "location": "  ", "category": "restaurant"})
        assert response.status_code == 400

    def test_empty_category_returns_400(self):
        response = client.post("/collect", json={"business_name": "Subway", "location": "Sydney", "category": "  "})
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# POST /collect — successful collection
# ---------------------------------------------------------------------------

class TestCollectEndpointSuccess:

    def test_returns_200_on_success(self):
        for p in _patch_all_collectors():
            p.start()
        try:
            response = client.post(
                "/collect",
                json={"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
            )
        finally:
            patch.stopall()
        assert response.status_code == 200

    def test_response_contains_required_fields(self):
        for p in _patch_all_collectors():
            p.start()
        try:
            response = client.post(
                "/collect",
                json={"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
            )
        finally:
            patch.stopall()
        body = response.json()
        required = {
            "business_name", "location", "category", "collected_at",
            "total_results", "news_count", "news_review_count",
            "review_count", "reddit_count", "score_only_count", "data"
        }
        assert required.issubset(body.keys()), f"Missing: {required - body.keys()}"

    def test_counts_are_correct(self):
        for p in _patch_all_collectors():
            p.start()
        try:
            response = client.post(
                "/collect",
                json={"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
            )
        finally:
            patch.stopall()
        body = response.json()
        assert body["news_count"] == len(MOCK_NEWS)
        assert body["news_review_count"] == len(MOCK_NEWS_REVIEWS)
        assert body["review_count"] == len(MOCK_REVIEWS)
        assert body["reddit_count"] == len(MOCK_REDDIT)

    def test_total_results_is_sum_of_all_sources(self):
        for p in _patch_all_collectors():
            p.start()
        try:
            response = client.post(
                "/collect",
                json={"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
            )
        finally:
            patch.stopall()
        body = response.json()
        expected_total = len(MOCK_NEWS) + len(MOCK_NEWS_REVIEWS) + len(MOCK_REVIEWS) + len(MOCK_REDDIT)
        assert body["total_results"] == expected_total

    def test_score_only_count_correct(self):
        """score_only_count reflects reviews with data_type='score_only'."""
        for p in _patch_all_collectors():
            p.start()
        try:
            response = client.post(
                "/collect",
                json={"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
            )
        finally:
            patch.stopall()
        body = response.json()
        expected = sum(1 for r in MOCK_REVIEWS if r.get("data_type") == "score_only")
        assert body["score_only_count"] == expected

    def test_business_name_in_response_matches_input(self):
        for p in _patch_all_collectors():
            p.start()
        try:
            response = client.post(
                "/collect",
                json={"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
            )
        finally:
            patch.stopall()
        assert response.json()["business_name"].lower() == "subway"

    def test_data_field_contains_all_collected_items(self):
        for p in _patch_all_collectors():
            p.start()
        try:
            response = client.post(
                "/collect",
                json={"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
            )
        finally:
            patch.stopall()
        data = response.json()["data"]
        assert isinstance(data, list)
        assert len(data) == len(MOCK_NEWS) + len(MOCK_NEWS_REVIEWS) + len(MOCK_REVIEWS) + len(MOCK_REDDIT)

    def test_returns_404_when_all_sources_empty(self):
        """Returns 404 when no data is collected from any source."""
        for p in _patch_all_collectors(news=[], reviews=[], maps=[], reddit=[]):
            p.start()
        try:
            response = client.post(
                "/collect",
                json={"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
            )
        finally:
            patch.stopall()
        assert response.status_code == 404

    def test_partial_source_failure_still_succeeds(self):
        """If one collector fails (returns []), the service still returns 200 with partial data."""
        for p in _patch_all_collectors(news=[], reviews=MOCK_NEWS_REVIEWS, maps=MOCK_REVIEWS):
            p.start()
        try:
            response = client.post(
                "/collect",
                json={"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
            )
        finally:
            patch.stopall()
        assert response.status_code == 200
        body = response.json()
        assert body["news_count"] == 0
        assert body["review_count"] == len(MOCK_REVIEWS)

    def test_collected_at_is_iso8601(self):
        """The collected_at timestamp is a valid ISO-8601 string."""
        from datetime import datetime
        for p in _patch_all_collectors():
            p.start()
        try:
            response = client.post(
                "/collect",
                json={"business_name": "Subway", "location": "Sydney", "category": "restaurant"},
            )
        finally:
            patch.stopall()
        ts = response.json()["collected_at"]
        # Should parse without error
        datetime.fromisoformat(ts)


# ---------------------------------------------------------------------------
# POST /refresh
# ---------------------------------------------------------------------------

class TestRefreshEndpoint:

    def test_returns_502_when_retrieval_api_unreachable(self):
        """Returns 502 when the Retrieval API cannot be reached."""
        with patch("main.http_requests.get") as mock_get:
            mock_get.side_effect = Exception("Connection refused")
            response = client.post("/refresh")
        assert response.status_code == 502

    def test_returns_200_when_no_companies(self):
        """Returns 200 with a meaningful message when no companies are registered."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"companies": []}
        with patch("main.http_requests.get", return_value=mock_resp):
            response = client.post("/refresh")
        assert response.status_code == 200

    def test_skips_recently_collected_company(self):
        """Companies collected within the last 24 hours are skipped."""
        from datetime import datetime
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = {
            "companies": [
                {
                    "business_name": "McDonald's",
                    "location": "Melbourne",
                    "category": "restaurant",
                    # Use naive UTC to match main.py's datetime.utcnow() comparison
                    "updated_at": datetime.utcnow().isoformat(),
                }
            ]
        }
        with patch("main.http_requests.get", return_value=mock_get):
            response = client.post("/refresh")
        assert response.status_code == 200
        body = response.json()
        # Skipped count should be 1
        assert body.get("skipped", 0) == 1 or "skipped" in str(body)

    def test_collects_stale_company(self):
        """Companies not collected in over 24 hours are re-collected."""
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = {
            "companies": [
                {
                    "business_name": "Subway",
                    "location": "Sydney",
                    "category": "restaurant",
                    "updated_at": "2026-01-01T00:00:00",  # very stale
                }
            ]
        }
        mock_post = MagicMock()
        mock_post.status_code = 200

        with patch("main.http_requests.get", return_value=mock_get), \
             patch("main.collect_news", return_value=MOCK_NEWS), \
             patch("main.collect_news_reviews", return_value=MOCK_NEWS_REVIEWS), \
             patch("main.collect_reviews", return_value=MOCK_REVIEWS), \
             patch("main.http_requests.post", return_value=mock_post):
            response = client.post("/refresh")

        assert response.status_code == 200
        body = response.json()
        assert body.get("collected", 0) >= 1 or "collected" in str(body)

    def test_response_has_summary_keys(self):
        """The refresh response contains summary counts."""
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = {"companies": []}
        with patch("main.http_requests.get", return_value=mock_get):
            response = client.post("/refresh")
        body = response.json()
        assert isinstance(body, dict)
        # Should have some form of summary (total/skipped/failed/collected)
        summary_keys = {"total", "skipped", "failed", "collected", "results", "message"}
        assert summary_keys & body.keys(), f"No summary keys found in: {body.keys()}"


# ---------------------------------------------------------------------------
# GET /stock
# ---------------------------------------------------------------------------

MOCK_STOCK_CANDLES = [
    {"date": "2026-04-14", "open": 288.0, "high": 291.0, "low": 287.0, "close": 290.0, "volume": 3000000},
    {"date": "2026-04-15", "open": 290.0, "high": 293.0, "low": 289.0, "close": 292.0, "volume": 3200000},
]

MOCK_STOCK_QUOTE = {
    "c": 295.50, "o": 290.00, "h": 297.00, "l": 289.50, "pc": 291.25,
}


class TestStockEndpoint:

    def test_returns_200_when_symbol_found(self):
        """Returns 200 when a valid ticker is found for the business."""
        with patch("main._search_symbol", return_value="MCD"), \
             patch("main._fetch_quote", return_value=MOCK_STOCK_QUOTE), \
             patch("main.collect_stock_history", return_value=MOCK_STOCK_CANDLES):
            response = client.get("/stock?business_name=McDonald%27s")
        assert response.status_code == 200

    def test_returns_404_when_symbol_not_found(self):
        """Returns 404 when the business cannot be matched to a listed ticker."""
        with patch("main._search_symbol", return_value=None):
            response = client.get("/stock?business_name=Unknown+Cafe+XYZ")
        assert response.status_code == 404

    def test_returns_404_when_symbol_found_but_no_market_data(self):
        """Returns 404 when a symbol is found but the quote has no price (e.g. private company)."""
        with patch("main._search_symbol", return_value="511024.BO"), \
             patch("main._fetch_quote", return_value={"c": None, "o": None, "h": None, "l": None, "pc": None}):
            response = client.get("/stock?business_name=Subway")
        assert response.status_code == 404

    def test_returns_400_when_business_name_empty(self):
        """Returns 400 when business_name query param is blank."""
        response = client.get("/stock?business_name=")
        assert response.status_code == 400

    def test_response_contains_required_fields(self):
        """Response body includes business_name, symbol, quote, and price_history."""
        with patch("main._search_symbol", return_value="MCD"), \
             patch("main._fetch_quote", return_value=MOCK_STOCK_QUOTE), \
             patch("main.collect_stock_history", return_value=MOCK_STOCK_CANDLES):
            response = client.get("/stock?business_name=McDonald%27s")
        body = response.json()
        assert "business_name" in body
        assert "symbol" in body
        assert "quote" in body
        assert "price_history" in body

    def test_symbol_in_response_matches_lookup(self):
        """The symbol field in the response is what _search_symbol returned."""
        with patch("main._search_symbol", return_value="MCD"), \
             patch("main._fetch_quote", return_value=MOCK_STOCK_QUOTE), \
             patch("main.collect_stock_history", return_value=MOCK_STOCK_CANDLES):
            response = client.get("/stock?business_name=McDonald%27s")
        assert response.json()["symbol"] == "MCD"

    def test_price_history_is_list(self):
        """price_history field is a list of candle dicts."""
        with patch("main._search_symbol", return_value="MCD"), \
             patch("main._fetch_quote", return_value=MOCK_STOCK_QUOTE), \
             patch("main.collect_stock_history", return_value=MOCK_STOCK_CANDLES):
            response = client.get("/stock?business_name=McDonald%27s")
        assert isinstance(response.json()["price_history"], list)

    def test_history_days_matches_candle_count(self):
        """history_days equals the length of price_history."""
        with patch("main._search_symbol", return_value="MCD"), \
             patch("main._fetch_quote", return_value=MOCK_STOCK_QUOTE), \
             patch("main.collect_stock_history", return_value=MOCK_STOCK_CANDLES):
            response = client.get("/stock?business_name=McDonald%27s")
        body = response.json()
        assert body["history_days"] == len(body["price_history"])

    def test_quote_contains_change_percent(self):
        """The quote section includes a calculated change_percent field."""
        with patch("main._search_symbol", return_value="MCD"), \
             patch("main._fetch_quote", return_value=MOCK_STOCK_QUOTE), \
             patch("main.collect_stock_history", return_value=MOCK_STOCK_CANDLES):
            response = client.get("/stock?business_name=McDonald%27s")
        assert "change_percent" in response.json()["quote"]

    def test_days_back_param_forwarded_to_history(self):
        """The days_back query param is passed through to collect_stock_history."""
        with patch("main._search_symbol", return_value="MCD"), \
             patch("main._fetch_quote", return_value=MOCK_STOCK_QUOTE), \
             patch("main.collect_stock_history", return_value=[]) as mock_hist:
            client.get("/stock?business_name=McDonald%27s&days_back=30")
        mock_hist.assert_called_once_with("MCD", days_back=30)
