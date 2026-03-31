"""
Pytest configuration — shared fixtures loaded automatically by pytest.
Mock data constants live in mock_data.py so they can be imported directly.
"""
import sys
import os

# Ensure project root is on the path so tests can import source modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Ensure tests/ itself is on the path so tests can do `from mock_data import ...`
sys.path.insert(0, os.path.dirname(__file__))
