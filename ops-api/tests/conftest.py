import sys
import os

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

# Make ops-api root importable as 'main'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main as ops_main


@pytest.fixture
def temporal_mock():
    handle = MagicMock()
    handle.id = "wf-test-123"
    client = AsyncMock()
    client.start_workflow = AsyncMock(return_value=handle)
    return client


@pytest.fixture
async def http_client(temporal_mock):
    """FastAPI test client with Temporal client injected (no lifespan connection)."""
    with patch.object(ops_main, "_temporal_client", temporal_mock):
        # raise_app_exceptions=False: tests see the 500 the client actually receives,
        # not the raw exception from the server. Matches real production behavior.
        async with AsyncClient(
            transport=ASGITransport(app=ops_main.app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            yield client
