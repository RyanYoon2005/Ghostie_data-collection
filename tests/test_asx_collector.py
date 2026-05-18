"""
Tests for ASXCollector.py — covers ticker resolution and announcement fetching.
All external HTTP calls are mocked so no real API keys are needed.
"""
from unittest.mock import MagicMock, patch

import ASXCollector
from ASXCollector import (
    _find_asx_ticker,
    _verify_asx_ticker,
    collect_asx_announcements,
)

# ---------------------------------------------------------------------------
# Shared mock announcement payloads
# ---------------------------------------------------------------------------

MOCK_MARKIT_ANNOUNCEMENT = {
    "documentKey": "2924-ann_001",
    "headline": "CBA Reports Record Half-Year Profit",
    "date": "2026-02-11T08:00:00.000Z",
    "isPriceSensitive": True,
    "url": "",
    "fileSize": "564KB",
}

MOCK_ASX_ANNOUNCEMENT = {
    "id": "ann_002",
    "header": "Origin Energy — Quarterly Activities Report",
    "document_release_date": "2026-04-15T10:30:00+11:00",
    "document_date": "2026-04-15",
    "market_sensitive": False,
    "url": "https://www.asx.com.au/asxpdf/20260415/pdf/ann_002.pdf",
    "number_of_pages": 12,
    "size": "1.2MB",
}


# ---------------------------------------------------------------------------
# _verify_asx_ticker
# ---------------------------------------------------------------------------


class TestVerifyAsxTicker:
    def test_returns_true_when_markit_returns_items_under_data(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"items": [MOCK_MARKIT_ANNOUNCEMENT]}}
        with patch("ASXCollector.requests.get", return_value=mock_resp):
            assert _verify_asx_ticker("CBA") is True

    def test_returns_true_when_markit_returns_top_level_items(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Markit always wraps under data.items — top-level items is legacy fallback
        mock_resp.json.return_value = {"data": {"items": [MOCK_MARKIT_ANNOUNCEMENT]}}
        with patch("ASXCollector.requests.get", return_value=mock_resp):
            assert _verify_asx_ticker("CBA") is True

    def test_falls_back_to_asx_api_when_markit_fails(self):
        markit_resp = MagicMock()
        markit_resp.status_code = 503

        asx_resp = MagicMock()
        asx_resp.status_code = 200
        asx_resp.json.return_value = {"data": [MOCK_ASX_ANNOUNCEMENT]}

        with patch("ASXCollector.requests.get", side_effect=[markit_resp, asx_resp]):
            assert _verify_asx_ticker("ORG") is True

    def test_returns_false_when_markit_returns_empty_items(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"items": []}}
        with patch("ASXCollector.requests.get", return_value=mock_resp):
            assert _verify_asx_ticker("XYZ") is False

    def test_returns_false_when_both_apis_raise_exception(self):
        with patch("ASXCollector.requests.get", side_effect=Exception("network error")):
            assert _verify_asx_ticker("CBA") is False

    def test_returns_false_when_markit_raises_and_asx_returns_empty(self):
        asx_resp = MagicMock()
        asx_resp.status_code = 200
        asx_resp.json.return_value = {"data": []}

        with patch("ASXCollector.requests.get", side_effect=[Exception("timeout"), asx_resp]):
            assert _verify_asx_ticker("XYZ") is False


# ---------------------------------------------------------------------------
# _find_asx_ticker
# ---------------------------------------------------------------------------


class TestFindAsxTicker:
    def test_resolves_commonwealth_bank_from_known_map(self):
        ticker = _find_asx_ticker("Commonwealth Bank")
        assert ticker == "CBA"

    def test_resolves_coles_from_known_map(self):
        ticker = _find_asx_ticker("Coles")
        assert ticker == "COL"

    def test_resolves_woolworths_from_known_map(self):
        ticker = _find_asx_ticker("Woolworths")
        assert ticker == "WOW"

    def test_known_map_match_is_case_insensitive(self):
        assert _find_asx_ticker("COMMONWEALTH BANK") == "CBA"
        assert _find_asx_ticker("commonwealth bank") == "CBA"

    def test_returns_none_when_no_api_key_and_not_in_map(self):
        original = ASXCollector.FINNHUB_API_KEY
        ASXCollector.FINNHUB_API_KEY = ""
        try:
            result = _find_asx_ticker("Some Unknown Company XYZ")
            assert result is None
        finally:
            ASXCollector.FINNHUB_API_KEY = original

    def test_uses_finnhub_when_not_in_known_map(self):
        finnhub_resp = MagicMock()
        finnhub_resp.status_code = 200
        finnhub_resp.json.return_value = {
            "result": [{"displaySymbol": "XRO.AX", "symbol": "XRO.AX"}]
        }

        markit_resp = MagicMock()
        markit_resp.status_code = 200
        markit_resp.json.return_value = {"data": {"items": [MOCK_MARKIT_ANNOUNCEMENT]}}

        with patch("ASXCollector.requests.get", side_effect=[finnhub_resp, markit_resp]):
            result = _find_asx_ticker("Xero")
            assert result == "XRO"

    def test_returns_none_when_finnhub_returns_no_candidates(self):
        finnhub_resp = MagicMock()
        finnhub_resp.status_code = 200
        finnhub_resp.json.return_value = {"result": []}

        mock_search = MagicMock()
        mock_search.quotes = []

        with patch("ASXCollector.requests.get", return_value=finnhub_resp):
            with patch("ASXCollector.yf.Search", return_value=mock_search):
                result = _find_asx_ticker("Totally Unknown Company")
                assert result is None

    def test_skips_candidate_with_invalid_asx_code(self):
        finnhub_resp = MagicMock()
        finnhub_resp.status_code = 200
        finnhub_resp.json.return_value = {
            "result": [
                {"displaySymbol": "TOOLONGCODE123", "symbol": "TOOLONGCODE123"},
            ]
        }

        mock_search = MagicMock()
        mock_search.quotes = []

        with patch("ASXCollector.requests.get", return_value=finnhub_resp):
            with patch("ASXCollector.yf.Search", return_value=mock_search):
                result = _find_asx_ticker("Some Company")
                assert result is None

    def test_yfinance_fallback_resolves_ticker(self):
        # Finnhub loop makes 2 calls (exchange=AU, then global) — both return empty
        finnhub_empty = MagicMock()
        finnhub_empty.status_code = 200
        finnhub_empty.json.return_value = {"result": []}

        mock_quote = {"symbol": "XRO.AX"}
        mock_search = MagicMock()
        mock_search.quotes = [mock_quote]

        # Third call: _verify_asx_ticker hits Markit for XRO
        markit_resp = MagicMock()
        markit_resp.status_code = 200
        markit_resp.json.return_value = {"data": {"items": [MOCK_MARKIT_ANNOUNCEMENT]}}

        with patch("ASXCollector.requests.get", side_effect=[finnhub_empty, finnhub_empty, markit_resp]):
            with patch("ASXCollector.yf.Search", return_value=mock_search):
                result = _find_asx_ticker("Xero")
                assert result == "XRO"

    def test_yfinance_fallback_skips_non_asx_symbols(self):
        finnhub_resp = MagicMock()
        finnhub_resp.status_code = 200
        finnhub_resp.json.return_value = {"result": []}

        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "AAPL"}, {"symbol": "GOOGL"}]

        with patch("ASXCollector.requests.get", return_value=finnhub_resp):
            with patch("ASXCollector.yf.Search", return_value=mock_search):
                result = _find_asx_ticker("Apple")
                assert result is None

    def test_yfinance_exception_is_handled_gracefully(self):
        finnhub_resp = MagicMock()
        finnhub_resp.status_code = 200
        finnhub_resp.json.return_value = {"result": []}

        # Use a name not in the hardcoded map or CSV so the test reaches yfinance
        with patch("ASXCollector.requests.get", return_value=finnhub_resp):
            with patch("ASXCollector.yf.Search", side_effect=Exception("yfinance down")):
                result = _find_asx_ticker("Nonexistent Company XYZ999")
                assert result is None

    def test_finnhub_exception_is_handled_gracefully(self):
        mock_search = MagicMock()
        mock_search.quotes = []

        # Use a name not in the hardcoded map or CSV so the test reaches Finnhub
        with patch("ASXCollector.requests.get", side_effect=Exception("network error")):
            with patch("ASXCollector.yf.Search", return_value=mock_search):
                result = _find_asx_ticker("Nonexistent Company XYZ999")
                assert result is None


# ---------------------------------------------------------------------------
# collect_asx_announcements
# ---------------------------------------------------------------------------


class TestCollectAsxAnnouncements:
    def test_returns_empty_list_for_unlisted_company(self):
        original = ASXCollector.FINNHUB_API_KEY
        ASXCollector.FINNHUB_API_KEY = ""
        try:
            result = collect_asx_announcements("Totally Unknown XYZ", "Sydney", "Finance")
            assert result == []
        finally:
            ASXCollector.FINNHUB_API_KEY = original

    def test_returns_announcements_from_markit_api(self):
        markit_resp = MagicMock()
        markit_resp.status_code = 200
        markit_resp.json.return_value = {"data": {"items": [MOCK_MARKIT_ANNOUNCEMENT]}}

        with patch("ASXCollector.requests.get", return_value=markit_resp):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert len(results) == 1
        assert results[0]["source"] == "asx_announcements"
        assert results[0]["publisher"] == "ASX (CBA)"

    def test_returns_announcements_from_asx_fallback(self):
        markit_fail = MagicMock()
        markit_fail.status_code = 503

        asx_resp = MagicMock()
        asx_resp.status_code = 200
        asx_resp.json.return_value = {"data": [MOCK_ASX_ANNOUNCEMENT]}

        with patch("ASXCollector.requests.get", side_effect=[markit_fail, asx_resp]):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert len(results) == 1
        assert results[0]["title"] == MOCK_ASX_ANNOUNCEMENT["header"]

    def test_returned_item_has_all_required_fields(self):
        markit_resp = MagicMock()
        markit_resp.status_code = 200
        markit_resp.json.return_value = {"data": {"items": [MOCK_MARKIT_ANNOUNCEMENT]}}

        with patch("ASXCollector.requests.get", return_value=markit_resp):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        item = results[0]
        for field in ("id", "source", "publisher", "timestamp", "query", "title", "body", "url", "data_type", "metadata"):
            assert field in item, f"Missing field: {field}"

    def test_query_metadata_embedded_correctly(self):
        markit_resp = MagicMock()
        markit_resp.status_code = 200
        markit_resp.json.return_value = {"data": {"items": [MOCK_MARKIT_ANNOUNCEMENT]}}

        with patch("ASXCollector.requests.get", return_value=markit_resp):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert results[0]["query"] == {
            "business_name": "Commonwealth Bank",
            "location": "Sydney",
            "category": "Finance",
        }

    def test_market_sensitive_flag_extracted_from_markit(self):
        markit_resp = MagicMock()
        markit_resp.status_code = 200
        markit_resp.json.return_value = {"data": {"items": [MOCK_MARKIT_ANNOUNCEMENT]}}

        with patch("ASXCollector.requests.get", return_value=markit_resp):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert results[0]["metadata"]["market_sensitive"] is True

    def test_market_sensitive_flag_extracted_from_asx_api(self):
        markit_fail = MagicMock()
        markit_fail.status_code = 503

        asx_resp = MagicMock()
        asx_resp.status_code = 200
        asx_resp.json.return_value = {"data": [MOCK_ASX_ANNOUNCEMENT]}

        with patch("ASXCollector.requests.get", side_effect=[markit_fail, asx_resp]):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert results[0]["metadata"]["market_sensitive"] is False

    def test_returns_empty_list_when_both_apis_return_no_data(self):
        markit_resp = MagicMock()
        markit_resp.status_code = 200
        markit_resp.json.return_value = {"data": {"items": []}}

        asx_resp = MagicMock()
        asx_resp.status_code = 200
        asx_resp.json.return_value = {"data": []}

        with patch("ASXCollector.requests.get", side_effect=[markit_resp, asx_resp]):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert results == []

    def test_returns_empty_list_when_markit_raises_and_asx_raises(self):
        with patch("ASXCollector.requests.get", side_effect=Exception("network error")):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert results == []

    def test_id_uses_ann_id_when_present(self):
        markit_resp = MagicMock()
        markit_resp.status_code = 200
        markit_resp.json.return_value = {"data": {"items": [MOCK_MARKIT_ANNOUNCEMENT]}}

        with patch("ASXCollector.requests.get", return_value=markit_resp):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert results[0]["id"] == "asx_CBA_2924-ann_001"

    def test_id_uses_hash_when_no_ann_id(self):
        ann_no_id = {**MOCK_MARKIT_ANNOUNCEMENT, "documentKey": ""}
        markit_resp = MagicMock()
        markit_resp.status_code = 200
        markit_resp.json.return_value = {"data": {"items": [ann_no_id]}}

        with patch("ASXCollector.requests.get", return_value=markit_resp):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert results[0]["id"].startswith("asx_CBA_")

    def test_url_falls_back_to_announcements_page_when_no_direct_url(self):
        ann = {**MOCK_ASX_ANNOUNCEMENT, "url": ""}
        markit_fail = MagicMock()
        markit_fail.status_code = 503

        asx_resp = MagicMock()
        asx_resp.status_code = 200
        asx_resp.json.return_value = {"data": [ann]}

        with patch("ASXCollector.requests.get", side_effect=[markit_fail, asx_resp]):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert results[0]["url"] == "https://www.asx.com.au/markets/company/CBA"

    def test_ticker_in_metadata(self):
        markit_resp = MagicMock()
        markit_resp.status_code = 200
        markit_resp.json.return_value = {"data": {"items": [MOCK_MARKIT_ANNOUNCEMENT]}}

        with patch("ASXCollector.requests.get", return_value=markit_resp):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert results[0]["metadata"]["ticker"] == "CBA"

    def test_asx_api_non_200_falls_through_to_empty(self):
        markit_fail = MagicMock()
        markit_fail.status_code = 503

        asx_fail = MagicMock()
        asx_fail.status_code = 404

        with patch("ASXCollector.requests.get", side_effect=[markit_fail, asx_fail]):
            results = collect_asx_announcements("Commonwealth Bank", "Sydney", "Finance")

        assert results == []
