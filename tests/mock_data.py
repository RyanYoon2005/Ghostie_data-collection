"""
Shared pytest fixtures and mock data for the Ghostie Data Collection test suite.
"""
import sys
import os
# Ensure project root is on the path so tests can import source modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Mock API response data
# ---------------------------------------------------------------------------

MOCK_NEWSAPI_ARTICLE = {
    "source": {"id": "bbc-news", "name": "BBC News"},
    "author": "Jane Doe",
    "title": "Subway opens new restaurant in Sydney",
    "description": "Subway has opened a brand new restaurant outlet in the heart of Sydney CBD.",
    "url": "https://bbc.com/news/subway-sydney-1",
    "publishedAt": "2026-03-20T10:00:00Z",
    "content": "Full article content here...",
}

MOCK_NEWSAPI_IRRELEVANT_ARTICLE = {
    "source": {"id": "nytimes", "name": "New York Times"},
    "author": "John Smith",
    "title": "Australian housing market sees record prices",
    "description": "Property prices in major Australian cities hit record highs this quarter.",
    "url": "https://nytimes.com/housing-prices-1",
    "publishedAt": "2026-03-20T09:00:00Z",
    "content": "Housing market content...",
}

MOCK_NEWSAPI_RESPONSE = {
    "status": "ok",
    "totalResults": 2,
    "articles": [MOCK_NEWSAPI_ARTICLE, MOCK_NEWSAPI_IRRELEVANT_ARTICLE],
}

MOCK_NEWSAPI_EMPTY_RESPONSE = {
    "status": "ok",
    "totalResults": 0,
    "articles": [],
}

MOCK_SERP_SEARCH_RESPONSE = {
    "local_results": [
        {
            "title": "Subway",
            "address": "123 George St, Sydney NSW 2000",
            "rating": 4.2,
            "reviews": 350,
            "data_id": "ChIJtest1234",
            "place_id": "ChIJplace5678",
        }
    ]
}

MOCK_SERP_PLACE_RESULT_RESPONSE = {
    "local_results": [],
    "place_results": {
        "title": "Subway",
        "address": "123 George St, Sydney NSW 2000",
        "rating": 4.2,
        "reviews": 350,
        "data_id": "ChIJtest1234",
        "place_id": "ChIJplace5678",
    },
}

MOCK_SERP_REVIEWS_RESPONSE = {
    "reviews": [
        {
            "review_id": "review_abc",
            "user": {"name": "Alice"},
            "rating": 5,
            "snippet": "Amazing sandwiches, great service!",
            "date": "2 weeks ago",
            "iso_date": "2026-03-15T00:00:00Z",
            "likes": 3,
        },
        {
            "review_id": "review_def",
            "user": {"name": "Bob"},
            "rating": 2,
            "snippet": "",  # score-only review
            "date": "1 month ago",
            "iso_date": "2026-02-15T00:00:00Z",
            "likes": 0,
        },
    ]
}

MOCK_FINNHUB_SEARCH_RESPONSE = {
    "count": 2,
    "result": [
        {"description": "MCDONALD'S CORP", "displaySymbol": "MCD", "symbol": "MCD", "type": "Common Stock"},
        {"description": "MCDONALD'S HOLDINGS CO JAPAN", "displaySymbol": "2702", "symbol": "2702", "type": "Common Stock"},
    ],
}

MOCK_FINNHUB_SEARCH_EXACT_RESPONSE = {
    "count": 1,
    "result": [
        {"description": "subway", "displaySymbol": "SUBW", "symbol": "SUBW", "type": "Common Stock"},
    ],
}

MOCK_FINNHUB_SEARCH_EMPTY_RESPONSE = {
    "count": 0,
    "result": [],
}

MOCK_FINNHUB_QUOTE_RESPONSE = {
    "c":  295.50,   # current price
    "o":  290.00,   # open
    "h":  297.00,   # high
    "l":  289.50,   # low
    "pc": 291.25,   # previous close
    "t":  1748000000,
}

MOCK_FINNHUB_NEWS_RESPONSE = [
    {
        "category": "company news",
        "datetime": 1748000000,
        "headline": "McDonald's reports strong Q1 earnings",
        "id": 123456,
        "image": "https://example.com/img.jpg",
        "related": "MCD",
        "source": "Reuters",
        "summary": "McDonald's Corporation reported better-than-expected Q1 earnings.",
        "url": "https://reuters.com/mcd-earnings",
    }
]

MOCK_FINNHUB_CANDLE_RESPONSE = {
    "s": "ok",
    "t": [1745000000, 1745086400, 1745172800],
    "o": [288.0, 290.0, 292.0],
    "h": [291.0, 293.0, 295.0],
    "l": [287.0, 289.0, 291.0],
    "c": [290.0, 292.0, 294.0],
    "v": [3000000, 3200000, 2900000],
}

MOCK_FINNHUB_CANDLE_NO_DATA_RESPONSE = {
    "s": "no_data",
}

MOCK_RETRIEVAL_COMPANIES_RESPONSE = {
    "companies": [
        {
            "business_name": "Subway",
            "location": "Sydney",
            "category": "restaurant",
            "updated_at": "2026-01-01T00:00:00",  # stale — should be re-collected
        },
        {
            "business_name": "McDonald's",
            "location": "Melbourne",
            "category": "restaurant",
            "updated_at": "2026-03-31T00:00:00",  # recent — should be skipped
        },
    ]
}
