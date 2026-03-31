"""
Unit tests for ReviewCollector.py

Level of abstraction: Unit
- All external HTTP calls (SerpAPI) are mocked with unittest.mock.
- Tests verify that collect_reviews() correctly transforms SerpAPI data,
  classifies score-only vs text reviews, and handles API failures gracefully.
"""
import pytest
from unittest.mock import patch, MagicMock, call

from mock_data import (
    MOCK_SERP_SEARCH_RESPONSE,
    MOCK_SERP_PLACE_RESULT_RESPONSE,
    MOCK_SERP_REVIEWS_RESPONSE,
)
from ReviewCollector import collect_reviews


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    return mock


def _make_search_then_reviews_mock(search_response, reviews_response):
    """Return a side_effect list: first call = search, second call = reviews."""
    return [search_response, reviews_response]


# ---------------------------------------------------------------------------
# collect_reviews()
# ---------------------------------------------------------------------------

class TestCollectReviews:

    def test_returns_list_of_reviews(self):
        """collect_reviews returns a list of reviews on success."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_SEARCH_RESPONSE),
                _mock_response(200, MOCK_SERP_REVIEWS_RESPONSE),
            )
            result = collect_reviews("Subway", "Sydney", "restaurant")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_reviews_have_required_fields(self):
        """Each review dict contains the required standardized fields."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_SEARCH_RESPONSE),
                _mock_response(200, MOCK_SERP_REVIEWS_RESPONSE),
            )
            result = collect_reviews("Subway", "Sydney", "restaurant")
        required = {"id", "source", "publisher", "timestamp", "query", "title", "body", "url", "metadata", "data_type"}
        for review in result:
            assert required.issubset(review.keys()), (
                f"Review missing: {required - review.keys()}"
            )

    def test_source_is_google_maps_reviews(self):
        """All reviews have source='google_maps_reviews'."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_SEARCH_RESPONSE),
                _mock_response(200, MOCK_SERP_REVIEWS_RESPONSE),
            )
            result = collect_reviews("Subway", "Sydney", "restaurant")
        for review in result:
            assert review["source"] == "google_maps_reviews"

    def test_text_review_classified_correctly(self):
        """Reviews with a snippet are classified as data_type='text_review'."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_SEARCH_RESPONSE),
                _mock_response(200, MOCK_SERP_REVIEWS_RESPONSE),
            )
            result = collect_reviews("Subway", "Sydney", "restaurant")
        text_reviews = [r for r in result if r["data_type"] == "text_review"]
        assert len(text_reviews) >= 1
        assert any("Amazing" in r["body"] for r in text_reviews)

    def test_score_only_review_classified_correctly(self):
        """Reviews without a snippet are classified as data_type='score_only'."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_SEARCH_RESPONSE),
                _mock_response(200, MOCK_SERP_REVIEWS_RESPONSE),
            )
            result = collect_reviews("Subway", "Sydney", "restaurant")
        score_only = [r for r in result if r["data_type"] == "score_only"]
        assert len(score_only) >= 1

    def test_rating_in_metadata(self):
        """Each review contains the star rating in metadata.rating."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_SEARCH_RESPONSE),
                _mock_response(200, MOCK_SERP_REVIEWS_RESPONSE),
            )
            result = collect_reviews("Subway", "Sydney", "restaurant")
        for review in result:
            assert "rating" in review["metadata"]
            assert review["metadata"]["rating"] is not None

    def test_likes_in_metadata(self):
        """Each review contains the likes count in metadata.likes."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_SEARCH_RESPONSE),
                _mock_response(200, MOCK_SERP_REVIEWS_RESPONSE),
            )
            result = collect_reviews("Subway", "Sydney", "restaurant")
        for review in result:
            assert "likes" in review["metadata"]

    def test_query_embedded_in_result(self):
        """Each review embeds the original query parameters."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_SEARCH_RESPONSE),
                _mock_response(200, MOCK_SERP_REVIEWS_RESPONSE),
            )
            result = collect_reviews("Subway", "Sydney", "restaurant")
        for review in result:
            assert review["query"]["business_name"] == "Subway"
            assert review["query"]["location"] == "Sydney"

    def test_returns_empty_list_when_search_api_fails(self):
        """Returns an empty list (does not raise) when the search API returns an error."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(500, {})
            result = collect_reviews("Subway", "Sydney", "restaurant")
        assert result == []

    def test_returns_empty_list_when_no_local_results(self):
        """Returns an empty list when no local_results or place_results are found."""
        empty_search = {"local_results": []}
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, empty_search)
            result = collect_reviews("Subway", "Sydney", "restaurant")
        assert result == []

    def test_falls_back_to_place_results(self):
        """Uses place_results when local_results is absent (exact business match)."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_PLACE_RESULT_RESPONSE),
                _mock_response(200, MOCK_SERP_REVIEWS_RESPONSE),
            )
            result = collect_reviews("Subway", "Sydney", "restaurant")
        assert len(result) > 0

    def test_returns_empty_list_when_data_id_missing(self):
        """Returns an empty list when the top result has no data_id."""
        no_data_id_response = {
            "local_results": [
                {"title": "Subway", "address": "Sydney", "rating": 4.0}
                # no data_id
            ]
        }
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, no_data_id_response)
            result = collect_reviews("Subway", "Sydney", "restaurant")
        assert result == []

    def test_returns_empty_list_when_reviews_api_fails(self):
        """Returns empty list when the reviews fetch call (second API call) fails."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_SEARCH_RESPONSE),
                _mock_response(500, {}),
            )
            result = collect_reviews("Subway", "Sydney", "restaurant")
        assert result == []

    def test_returns_empty_list_when_no_reviews_key(self):
        """Returns empty list when the reviews API response has no 'reviews' key."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_SEARCH_RESPONSE),
                _mock_response(200, {"error": "No reviews found"}),
            )
            result = collect_reviews("Subway", "Sydney", "restaurant")
        assert result == []

    def test_second_api_call_uses_data_id(self):
        """The reviews fetch call passes the data_id from the search result."""
        with patch("ReviewCollector.requests.get") as mock_get:
            mock_get.side_effect = _make_search_then_reviews_mock(
                _mock_response(200, MOCK_SERP_SEARCH_RESPONSE),
                _mock_response(200, MOCK_SERP_REVIEWS_RESPONSE),
            )
            collect_reviews("Subway", "Sydney", "restaurant")
        # Second call must include the data_id from the first result
        second_call_params = mock_get.call_args_list[1][1]["params"]
        assert second_call_params.get("data_id") == "ChIJtest1234"
