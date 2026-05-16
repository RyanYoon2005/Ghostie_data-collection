"""
Pytest configuration — shared fixtures loaded automatically by pytest.
Mock data constants live in mock_data.py so they can be imported directly.
"""
import sys
import os

# Set required env vars before any source modules are imported
os.environ.setdefault("NEWSAPI_KEY", "test-key")
os.environ.setdefault("SERP_API_KEY", "test-key")
os.environ.setdefault("FINNHUB_API_KEY", "test-key")
os.environ.setdefault("RETRIEVAL_API_BASE", "https://fake-api.example.com")

# Ensure project root is on the path so tests can import source modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Ensure tests/ itself is on the path so tests can do `from mock_data import ...`
sys.path.insert(0, os.path.dirname(__file__))
