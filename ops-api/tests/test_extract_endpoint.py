"""Unit tests for the ops-api FastAPI endpoints. Temporal and Supabase are mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# /healthz
# ---------------------------------------------------------------------------

async def test_healthz_returns_ok(http_client):
    resp = await http_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /extract — validation
# ---------------------------------------------------------------------------

async def test_extract_empty_notes_returns_400(http_client):
    resp = await http_client.post("/extract", json={"notes": ""})
    assert resp.status_code == 400


async def test_extract_whitespace_only_notes_returns_400(http_client):
    resp = await http_client.post("/extract", json={"notes": "   "})
    assert resp.status_code == 400


async def test_extract_missing_body_returns_422(http_client):
    """No JSON body at all — Pydantic must reject it before the handler runs."""
    resp = await http_client.post("/extract")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /extract — success path
# ---------------------------------------------------------------------------

def _mock_supabase_http():
    mock_http = MagicMock()
    mock_http.post.return_value = MagicMock(status_code=201, text="")
    mock_http.patch.return_value = MagicMock(status_code=200, text="")
    return mock_http


async def test_extract_returns_session_and_workflow_id(http_client):
    mock_http = _mock_supabase_http()
    with patch("httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value = mock_http
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        resp = await http_client.post("/extract", json={"notes": "Alice will fix the login bug by Friday."})

    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "workflow_id" in data
    assert data["workflow_id"] == "wf-test-123"


async def test_extract_creates_pending_session_in_supabase(http_client):
    mock_http = _mock_supabase_http()
    with patch("httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value = mock_http
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        resp = await http_client.post("/extract", json={"notes": "Bob will deploy by end of week."})

    assert resp.status_code == 200
    post_call = mock_http.post.call_args
    assert post_call is not None
    # Correct Supabase endpoint
    assert "/rest/v1/meeting_sessions" in post_call.args[0]
    payload = post_call.kwargs["json"]
    assert payload["status"] == "pending"
    assert payload["notes"] == "Bob will deploy by end of week."
    # A UUID was generated
    assert len(payload["id"]) == 36


async def test_extract_starts_correct_temporal_workflow(http_client, temporal_mock):
    """Verifies workflow name, input contents, and workflow ID format."""
    mock_http = _mock_supabase_http()
    notes = "Carol will write docs by Thursday."
    with patch("httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value = mock_http
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        resp = await http_client.post("/extract", json={"notes": notes})

    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    temporal_mock.start_workflow.assert_called_once()
    call_args = temporal_mock.start_workflow.call_args

    # Workflow type name
    assert call_args.args[0] == "MeetingNotesWorkflow"

    # Input carries correct session_id and notes
    wf_input = call_args.args[1]
    assert wf_input.session_id == session_id
    assert wf_input.notes == notes

    # Workflow ID follows the expected convention
    assert call_args.kwargs["id"] == f"meeting-notes-{session_id}"
    assert call_args.kwargs["task_queue"] == "main"


# ---------------------------------------------------------------------------
# /extract — error paths
# ---------------------------------------------------------------------------

async def test_extract_supabase_failure_returns_500(http_client):
    mock_http = MagicMock()
    mock_http.post.return_value = MagicMock(status_code=500, text="DB error")
    with patch("httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value = mock_http
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        resp = await http_client.post("/extract", json={"notes": "Valid notes about the project."})

    assert resp.status_code == 500


async def test_extract_temporal_failure_returns_500(http_client, temporal_mock):
    """If Temporal is unreachable, the endpoint must return 500."""
    temporal_mock.start_workflow.side_effect = Exception("Temporal unreachable")
    mock_http = _mock_supabase_http()
    with patch("httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value = mock_http
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        resp = await http_client.post("/extract", json={"notes": "Dave will update the docs tomorrow."})

    assert resp.status_code == 500
