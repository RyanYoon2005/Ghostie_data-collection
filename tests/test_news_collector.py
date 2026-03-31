"""
Unit tests for NewsCollector.py

Level of abstraction: Unit
- All external HTTP calls (NewsAPI) are mocked with unittest.mock.
- Tests verify the transformation, filtering, and error-handling logic
  inside collect_news() and collect_news_reviews() in complete isolation.
"""
import pytest
from unittest.mock import patch, MagicMock

from mock_data import (
    MOCK_NEWSAPI_RESPONSE,
    MOCK_NEWSAPI_EMPTY_RESPONSE,
    MOCK_NEWSAPI_ARTICLE,
    MOCK_NEWSAPI_IRRELEVANT_ARTICLE,
)
from NewsCollector import collect_news, collect_news_reviews


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.text = str(json_data)
    return mock


# ---------------------------------------------------------------------------
# collect_news()
# ---------------------------------------------------------------------------

class TestCollectNews:

    def test_returns_list_of_articles(self):
        """collect_news returns a list when the API succeeds."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_RESPONSE)
            result = collect_news("Subway", "Sydney", "restaurant")
        assert isinstance(result, list)

    def test_articles_have_required_fields(self):
        """Every returned article contains the required standardized fields."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_RESPONSE)
            result = collect_news("Subway", "Sydney", "restaurant")

        required_fields = {"id", "source", "publisher", "timestamp", "query", "title", "body", "url", "metadata"}
        for article in result:
            assert required_fields.issubset(article.keys()), (
                f"Article missing fields: {required_fields - article.keys()}"
            )

    def test_source_field_is_newsapi(self):
        """All articles from collect_news must have source='newsapi'."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_RESPONSE)
            result = collect_news("Subway", "Sydney", "restaurant")
        for article in result:
            assert article["source"] == "newsapi"

    def test_query_metadata_embedded_in_result(self):
        """Each article embeds the original query parameters."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_RESPONSE)
            result = collect_news("Subway", "Sydney", "restaurant")
        for article in result:
            assert article["query"]["business_name"] == "Subway"
            assert article["query"]["location"] == "Sydney"
            assert article["query"]["category"] == "restaurant"

    def test_relevance_filter_removes_irrelevant_articles(self):
        """Articles that don't mention the business name are filtered out."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_RESPONSE)
            # MOCK_NEWSAPI_RESPONSE has 1 relevant (Subway sandwich) and 1 irrelevant (NYC transit)
            result = collect_news("Subway", "Sydney", "restaurant")
        # Only the sandwich article should pass the filter
        assert len(result) == 1
        assert "subway" in result[0]["title"].lower()

    def test_id_uses_url_hash(self):
        """Article ID is derived from the article URL."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_RESPONSE)
            result = collect_news("Subway", "Sydney", "restaurant")
        assert result[0]["id"].startswith("news_")

    def test_returns_empty_list_when_no_articles(self):
        """Returns an empty list when the API returns zero results."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_EMPTY_RESPONSE)
            result = collect_news("Subway", "Sydney", "restaurant")
        assert result == []

    def test_returns_empty_list_on_api_error(self):
        """Returns an empty list (does not raise) when NewsAPI returns an error."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(401, {"message": "API key invalid"})
            result = collect_news("Subway", "Sydney", "restaurant")
        assert result == []

    def test_returns_empty_list_on_500_error(self):
        """Returns an empty list when the API returns a server error."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(500, {})
            result = collect_news("Subway", "Sydney", "restaurant")
        assert result == []

    def test_retries_on_426_plan_limit(self):
        """On a 426 response, the function retries with an adjusted date."""
        ok_response   = _mock_response(200, MOCK_NEWSAPI_RESPONSE)
        plan_response = _mock_response(426, {})
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.side_effect = [plan_response, ok_response]
            result = collect_news("Subway", "Sydney", "restaurant")
        assert mock_get.call_count == 2
        assert isinstance(result, list)

    def test_days_back_capped_at_29(self):
        """days_back is silently capped to MAX_DAYS_BACK=29 for the free tier."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_EMPTY_RESPONSE)
            collect_news("Subway", "Sydney", "restaurant", days_back=9999)
        call_params = mock_get.call_args[1]["params"]
        from datetime import datetime, timedelta
        expected_from = datetime.now() - timedelta(days=29)
        actual_from   = datetime.strptime(call_params["from"], "%Y-%m-%d")
        diff_days = abs((expected_from - actual_from).days)
        assert diff_days <= 1  # allow 1-day tolerance for test timing

    def test_publisher_extracted_from_source_name(self):
        """The publisher field is taken from article['source']['name']."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_RESPONSE)
            result = collect_news("Subway", "Sydney", "restaurant")
        assert result[0]["publisher"] == "BBC News"

    def test_body_uses_description_field(self):
        """The body field is populated from the article's description."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_RESPONSE)
            result = collect_news("Subway", "Sydney", "restaurant")
        assert "Sydney" in result[0]["body"]

    def test_all_articles_irrelevant_returns_empty(self):
        """Returns empty list when all fetched articles fail the relevance filter."""
        only_irrelevant = {
            "status": "ok",
            "totalResults": 1,
            "articles": [MOCK_NEWSAPI_IRRELEVANT_ARTICLE],
        }
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, only_irrelevant)
            result = collect_news("Subway", "Sydney", "restaurant")
        assert result == []


# ---------------------------------------------------------------------------
# collect_news_reviews()
# ---------------------------------------------------------------------------

MOCK_NEWSAPI_REVIEW_ARTICLE = {
    "source": {"id": "timeout", "name": "Time Out"},
    "author": "Critic Jones",
    "title": "Subway Sydney review: a quick lunch done right",
    "description": "Our Subway Sydney review finds a surprisingly good lunch option in the CBD.",
    "url": "https://timeout.com/sydney/subway-review",
    "publishedAt": "2026-03-18T12:00:00Z",
    "content": "Review content...",
}

MOCK_NEWSAPI_REVIEW_RESPONSE = {
    "status": "ok",
    "totalResults": 1,
    "articles": [MOCK_NEWSAPI_REVIEW_ARTICLE],
}


class TestCollectNewsReviews:

    def test_returns_list_of_reviews(self):
        """collect_news_reviews returns a list on success."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_REVIEW_RESPONSE)
            result = collect_news_reviews("Subway", "Sydney", "restaurant")
        assert isinstance(result, list)

    def test_source_field_is_news_review(self):
        """All results have source='news_review' (not 'newsapi')."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_REVIEW_RESPONSE)
            result = collect_news_reviews("Subway", "Sydney", "restaurant")
        for item in result:
            assert item["source"] == "news_review"

    def test_id_prefixed_with_newsreview(self):
        """IDs for news reviews are prefixed 'newsreview_'."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_REVIEW_RESPONSE)
            result = collect_news_reviews("Subway", "Sydney", "restaurant")
        for item in result:
            assert item["id"].startswith("newsreview_")

    def test_articles_have_required_fields(self):
        """All fields required by the data model are present."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_REVIEW_RESPONSE)
            result = collect_news_reviews("Subway", "Sydney", "restaurant")
        required = {"id", "source", "publisher", "timestamp", "query", "title", "body", "url", "metadata"}
        for item in result:
            assert required.issubset(item.keys())

    def test_returns_empty_list_on_api_error(self):
        """Does not raise on API error — returns empty list."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(403, {"message": "Forbidden"})
            result = collect_news_reviews("Subway", "Sydney", "restaurant")
        assert result == []

    def test_retries_on_426_plan_limit(self):
        """Retries once when the free-tier date limit (HTTP 426) is hit."""
        ok_response   = _mock_response(200, MOCK_NEWSAPI_REVIEW_RESPONSE)
        plan_response = _mock_response(426, {})
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.side_effect = [plan_response, ok_response]
            result = collect_news_reviews("Subway", "Sydney", "restaurant")
        assert mock_get.call_count == 2

    def test_query_includes_review_keyword(self):
        """The query string sent to NewsAPI includes the word 'review'."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_EMPTY_RESPONSE)
            collect_news_reviews("Subway", "Sydney", "restaurant")
        call_params = mock_get.call_args[1]["params"]
        assert "review" in call_params["q"].lower()

    def test_returns_empty_list_when_no_articles(self):
        """Returns an empty list when the API has no results."""
        with patch("NewsCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_NEWSAPI_EMPTY_RESPONSE)
            result = collect_news_reviews("Subway", "Sydney", "restaurant")
        assert result == []
