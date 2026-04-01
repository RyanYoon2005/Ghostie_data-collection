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
