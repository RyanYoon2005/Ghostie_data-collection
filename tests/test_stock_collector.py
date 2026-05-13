"""
Unit tests for StockCollector.py

Level of abstraction: Unit
- All external HTTP calls (Finnhub API) are mocked with unittest.mock.
- Tests verify symbol search, quote fetching, candle history, and the full
  collect_stock_data() pipeline in isolation.
"""
import pytest
from unittest.mock import patch, MagicMock

from mock_data import (
    MOCK_FINNHUB_SEARCH_RESPONSE,
    MOCK_FINNHUB_SEARCH_EXACT_RESPONSE,
    MOCK_FINNHUB_SEARCH_EMPTY_RESPONSE,
    MOCK_FINNHUB_QUOTE_RESPONSE,
    MOCK_FINNHUB_NEWS_RESPONSE,
    MOCK_FINNHUB_CANDLE_RESPONSE,
    MOCK_FINNHUB_CANDLE_NO_DATA_RESPONSE,
)
from StockCollector import (
    _search_symbol,
    _fetch_quote,
    _fetch_company_news,
    collect_stock_history,
    collect_stock_data,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.text = str(json_data)
    return mock


# ---------------------------------------------------------------------------
# _search_symbol()
# ---------------------------------------------------------------------------

class TestSearchSymbol:

    def test_returns_top_result_symbol_when_no_exact_match(self):
        """Returns the first result's symbol when no exact name match exists."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_SEARCH_RESPONSE)
            result = _search_symbol("McDonald's")
        assert result == "MCD"

    def test_returns_exact_match_symbol_when_name_matches(self):
        """Prefers an exact description match over the top result."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_SEARCH_EXACT_RESPONSE)
            result = _search_symbol("subway")
        assert result == "SUBW"

    def test_returns_none_when_results_empty(self):
        """Returns None when the API returns an empty result list."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_SEARCH_EMPTY_RESPONSE)
            result = _search_symbol("Unknown Business XYZ")
        assert result is None

    def test_returns_none_on_api_error(self):
        """Returns None (does not raise) when Finnhub returns an error status."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(401, {"error": "Invalid token"})
            result = _search_symbol("McDonald's")
        assert result is None

    def test_search_query_sent_to_correct_endpoint(self):
        """Confirms the correct Finnhub /search endpoint is called."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_SEARCH_EMPTY_RESPONSE)
            _search_symbol("Subway")
        url = mock_get.call_args[0][0]
        assert "/search" in url


# ---------------------------------------------------------------------------
# _fetch_quote()
# ---------------------------------------------------------------------------

class TestFetchQuote:

    def test_returns_quote_dict_on_success(self):
        """Returns the full quote dict when Finnhub responds with 200."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_QUOTE_RESPONSE)
            result = _fetch_quote("MCD")
        assert result == MOCK_FINNHUB_QUOTE_RESPONSE

    def test_returns_none_on_api_error(self):
        """Returns None when Finnhub returns a non-200 status."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(403, {})
            result = _fetch_quote("MCD")
        assert result is None

    def test_quote_contains_current_price(self):
        """The returned quote includes the current price field 'c'."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_QUOTE_RESPONSE)
            result = _fetch_quote("MCD")
        assert "c" in result
        assert result["c"] == 295.50


# ---------------------------------------------------------------------------
# _fetch_company_news()
# ---------------------------------------------------------------------------

class TestFetchCompanyNews:

    def test_returns_list_of_articles_on_success(self):
        """Returns the news list when Finnhub responds with a JSON array."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_NEWS_RESPONSE)
            result = _fetch_company_news("MCD", "2026-04-01", "2026-05-01")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_returns_empty_list_on_api_error(self):
        """Returns [] (does not raise) when Finnhub returns an error."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(500, {})
            result = _fetch_company_news("MCD", "2026-04-01", "2026-05-01")
        assert result == []

    def test_returns_empty_list_when_response_is_not_a_list(self):
        """Returns [] when the API response body is not a JSON array."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, {"error": "unexpected format"})
            result = _fetch_company_news("MCD", "2026-04-01", "2026-05-01")
        assert result == []


# ---------------------------------------------------------------------------
# collect_stock_history()
# ---------------------------------------------------------------------------

class TestCollectStockHistory:

    def test_returns_list_of_candles_on_success(self):
        """Returns a list of OHLCV candle dicts when Finnhub responds with ok status."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_CANDLE_RESPONSE)
            result = collect_stock_history("MCD")
        assert isinstance(result, list)
        assert len(result) == 3

    def test_candles_have_required_fields(self):
        """Each candle contains date, open, high, low, close, volume."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_CANDLE_RESPONSE)
            result = collect_stock_history("MCD")
        required = {"date", "open", "high", "low", "close", "volume"}
        for candle in result:
            assert required.issubset(candle.keys())

    def test_date_field_is_formatted_yyyy_mm_dd(self):
        """Date strings are formatted as YYYY-MM-DD."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_CANDLE_RESPONSE)
            result = collect_stock_history("MCD")
        from datetime import datetime
        for candle in result:
            datetime.strptime(candle["date"], "%Y-%m-%d")  # raises if format wrong

    def test_returns_empty_list_when_status_is_no_data(self):
        """Returns [] when Finnhub candle status is 'no_data'."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_CANDLE_NO_DATA_RESPONSE)
            result = collect_stock_history("MCD")
        assert result == []

    def test_returns_empty_list_on_api_error(self):
        """Returns [] when the Finnhub candle endpoint returns non-200."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(500, {})
            result = collect_stock_history("MCD")
        assert result == []

    def test_days_back_capped_at_365(self):
        """days_back is silently capped to MAX_CANDLE_DAYS=365."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_CANDLE_NO_DATA_RESPONSE)
            collect_stock_history("MCD", days_back=9999)
        # Verify the function still runs without error (cap is internal)
        assert mock_get.call_count == 1

    def test_volume_is_integer(self):
        """Volume values are converted to int."""
        with patch("StockCollector.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, MOCK_FINNHUB_CANDLE_RESPONSE)
            result = collect_stock_history("MCD")
        for candle in result:
            assert isinstance(candle["volume"], int)


# ---------------------------------------------------------------------------
# collect_stock_data()
# ---------------------------------------------------------------------------

class TestCollectStockData:

    def test_returns_empty_list_when_no_api_key(self):
        """Returns [] immediately when FINNHUB_API_KEY is not set."""
        with patch("StockCollector.API_KEY", ""):
            result = collect_stock_data("McDonald's", "Sydney", "restaurant")
        assert result == []

    def test_returns_empty_list_when_symbol_not_found(self):
        """Returns [] when business cannot be matched to a ticker."""
        with patch("StockCollector._search_symbol", return_value=None):
            result = collect_stock_data("Unknown Cafe XYZ", "Sydney", "restaurant")
        assert result == []

    def test_returns_list_with_quote_and_news_on_success(self):
        """Returns standardized items for both quote and news when all API calls succeed."""
        with patch("StockCollector._search_symbol", return_value="MCD"), \
             patch("StockCollector._fetch_quote", return_value=MOCK_FINNHUB_QUOTE_RESPONSE), \
             patch("StockCollector._fetch_company_news", return_value=MOCK_FINNHUB_NEWS_RESPONSE):
            result = collect_stock_data("McDonald's", "Australia", "restaurant")
        assert isinstance(result, list)
        assert len(result) == 2  # 1 quote item + 1 news item

    def test_quote_item_has_correct_source(self):
        """The stock quote item has source='finnhub_quote'."""
        with patch("StockCollector._search_symbol", return_value="MCD"), \
             patch("StockCollector._fetch_quote", return_value=MOCK_FINNHUB_QUOTE_RESPONSE), \
             patch("StockCollector._fetch_company_news", return_value=[]):
            result = collect_stock_data("McDonald's", "Australia", "restaurant")
        quote_items = [r for r in result if r["source"] == "finnhub_quote"]
        assert len(quote_items) == 1

    def test_news_item_has_correct_source(self):
        """News items have source='finnhub_news'."""
        with patch("StockCollector._search_symbol", return_value="MCD"), \
             patch("StockCollector._fetch_quote", return_value=MOCK_FINNHUB_QUOTE_RESPONSE), \
             patch("StockCollector._fetch_company_news", return_value=MOCK_FINNHUB_NEWS_RESPONSE):
            result = collect_stock_data("McDonald's", "Australia", "restaurant")
        news_items = [r for r in result if r["source"] == "finnhub_news"]
        assert len(news_items) == 1

    def test_items_have_required_fields(self):
        """All returned items contain the standard data model fields."""
        with patch("StockCollector._search_symbol", return_value="MCD"), \
             patch("StockCollector._fetch_quote", return_value=MOCK_FINNHUB_QUOTE_RESPONSE), \
             patch("StockCollector._fetch_company_news", return_value=MOCK_FINNHUB_NEWS_RESPONSE):
            result = collect_stock_data("McDonald's", "Australia", "restaurant")
        required = {"id", "source", "publisher", "timestamp", "query", "title", "body", "url", "metadata"}
        for item in result:
            assert required.issubset(item.keys())

    def test_query_embedded_in_all_items(self):
        """All items embed the original query parameters."""
        with patch("StockCollector._search_symbol", return_value="MCD"), \
             patch("StockCollector._fetch_quote", return_value=MOCK_FINNHUB_QUOTE_RESPONSE), \
             patch("StockCollector._fetch_company_news", return_value=MOCK_FINNHUB_NEWS_RESPONSE):
            result = collect_stock_data("McDonald's", "Australia", "restaurant")
        for item in result:
            assert item["query"]["business_name"] == "McDonald's"
            assert item["query"]["location"] == "Australia"
            assert item["query"]["category"] == "restaurant"

    def test_change_percent_calculated_correctly(self):
        """change_percent in quote metadata is correctly derived from c and pc."""
        with patch("StockCollector._search_symbol", return_value="MCD"), \
             patch("StockCollector._fetch_quote", return_value=MOCK_FINNHUB_QUOTE_RESPONSE), \
             patch("StockCollector._fetch_company_news", return_value=[]):
            result = collect_stock_data("McDonald's", "Australia", "restaurant")
        quote_item = next(r for r in result if r["source"] == "finnhub_quote")
        # (295.50 - 291.25) / 291.25 * 100 ≈ 1.46
        change = quote_item["metadata"]["change_percent"]
        assert change is not None
        assert abs(change - 1.46) < 0.1

    def test_skips_quote_item_when_quote_is_none(self):
        """No quote item is added when _fetch_quote returns None."""
        with patch("StockCollector._search_symbol", return_value="MCD"), \
             patch("StockCollector._fetch_quote", return_value=None), \
             patch("StockCollector._fetch_company_news", return_value=MOCK_FINNHUB_NEWS_RESPONSE):
            result = collect_stock_data("McDonald's", "Australia", "restaurant")
        quote_items = [r for r in result if r["source"] == "finnhub_quote"]
        assert len(quote_items) == 0

    def test_returns_empty_list_when_no_quote_and_no_news(self):
        """Returns an empty list when both quote and news are unavailable."""
        with patch("StockCollector._search_symbol", return_value="MCD"), \
             patch("StockCollector._fetch_quote", return_value=None), \
             patch("StockCollector._fetch_company_news", return_value=[]):
            result = collect_stock_data("McDonald's", "Australia", "restaurant")
        assert result == []
