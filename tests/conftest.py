"""Shared fixtures for tests."""

import pytest
from unittest.mock import MagicMock, patch

import openai

from agent.chat import CensusAgent, ChatSession


@pytest.fixture
def mock_snowflake_conn():
    """A mocked Snowflake connection."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    return conn


@pytest.fixture
def mock_openai_client():
    """A mocked OpenAI client."""
    client = MagicMock(spec=openai.OpenAI)
    return client


@pytest.fixture
def agent(mock_openai_client, mock_snowflake_conn):
    """A CensusAgent with mocked dependencies."""
    a = CensusAgent(mock_openai_client, mock_snowflake_conn)
    # Pre-populate schema cache to skip discovery
    a._schema_cache = "-- Table: POPULATION\n  STATE VARCHAR\n  POPULATION INTEGER\n  YEAR INTEGER"
    return a


@pytest.fixture
def session():
    """A fresh ChatSession."""
    return ChatSession()
