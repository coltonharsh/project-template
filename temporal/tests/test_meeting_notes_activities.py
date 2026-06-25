"""
Unit tests for save_action_items and mark_session_failed.
Supabase is always mocked (httpx.Client patched).

Integration tests (marked 'integration') require:
  SUPABASE_URL=http://localhost:54321
  SUPABASE_SERVICE_ROLE_KEY=<real key>
  and a running local Supabase stack.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.activities.meeting_notes import (
    MarkFailedInput,
    SaveActionItemsInput,
    mark_session_failed,
    save_action_items,
)

SESSION_ID = "test-session-00000000"
ITEMS = [
    {"task": "Fix bug", "owner": "Alice", "due_date": "Friday"},
    {"task": "Review PR", "owner": "Bob", "due_date": "Monday"},
]


def _mock_http(post_status: int = 201, patch_status: int = 200) -> MagicMock:
    """Return a mock httpx client context-manager with configurable status codes."""
    mock = MagicMock()
    post_resp = MagicMock(status_code=post_status)
    patch_resp = MagicMock(status_code=patch_status)
    # Default raise_for_status is a no-op for success statuses
    post_resp.raise_for_status = MagicMock()
    patch_resp.raise_for_status = MagicMock()
    mock.post.return_value = post_resp
    mock.patch.return_value = patch_resp
    return mock


def _patch_httpx(mock_http: MagicMock):
    return patch("httpx.Client", **{
        "return_value.__enter__.return_value": mock_http,
        "return_value.__exit__": MagicMock(return_value=False),
    })


# ---------------------------------------------------------------------------
# save_action_items — payload
# ---------------------------------------------------------------------------

def test_save_posts_action_item_rows():
    mock_http = _mock_http()
    with _patch_httpx(mock_http):
        save_action_items(SaveActionItemsInput(session_id=SESSION_ID, items=ITEMS))

    post_call = mock_http.post.call_args
    assert post_call is not None
    # Verify the correct Supabase endpoint is called
    assert "/rest/v1/action_items" in post_call.args[0]
    rows = post_call.kwargs["json"]
    assert len(rows) == 2
    assert rows[0]["session_id"] == SESSION_ID
    assert rows[0]["task"] == "Fix bug"
    assert rows[0]["owner"] == "Alice"
    assert rows[1]["task"] == "Review PR"


def test_save_patches_session_to_completed():
    mock_http = _mock_http()
    with _patch_httpx(mock_http):
        save_action_items(SaveActionItemsInput(session_id=SESSION_ID, items=ITEMS))

    patch_call = mock_http.patch.call_args
    assert patch_call is not None
    assert "/rest/v1/meeting_sessions" in patch_call.args[0]
    assert patch_call.kwargs["json"]["status"] == "completed"
    assert f"eq.{SESSION_ID}" in patch_call.kwargs["params"]["id"]


def test_save_empty_items_skips_insert_but_marks_completed():
    mock_http = _mock_http()
    with _patch_httpx(mock_http):
        save_action_items(SaveActionItemsInput(session_id=SESSION_ID, items=[]))

    mock_http.post.assert_not_called()
    mock_http.patch.assert_called_once()
    assert mock_http.patch.call_args.kwargs["json"]["status"] == "completed"


# ---------------------------------------------------------------------------
# save_action_items — auth headers
# ---------------------------------------------------------------------------

def test_save_sends_auth_headers(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key-abc")
    mock_http = _mock_http()
    with _patch_httpx(mock_http):
        save_action_items(SaveActionItemsInput(session_id=SESSION_ID, items=ITEMS))

    post_call = mock_http.post.call_args
    headers = post_call.kwargs["headers"]
    assert headers["apikey"] == "test-service-key-abc"
    assert "test-service-key-abc" in headers["Authorization"]


# ---------------------------------------------------------------------------
# save_action_items — HTTP error propagation
# ---------------------------------------------------------------------------

def test_save_propagates_supabase_post_error(monkeypatch):
    """If the action_items INSERT fails, the error must not be silently swallowed."""
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    mock_http = _mock_http()
    mock_http.post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error",
        request=MagicMock(),
        response=MagicMock(status_code=500),
    )
    with _patch_httpx(mock_http):
        with pytest.raises(httpx.HTTPStatusError):
            save_action_items(SaveActionItemsInput(session_id=SESSION_ID, items=ITEMS))


def test_save_propagates_supabase_patch_error(monkeypatch):
    """If the session PATCH fails, the error must not be swallowed."""
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    mock_http = _mock_http()
    mock_http.patch.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error",
        request=MagicMock(),
        response=MagicMock(status_code=500),
    )
    with _patch_httpx(mock_http):
        with pytest.raises(httpx.HTTPStatusError):
            save_action_items(SaveActionItemsInput(session_id=SESSION_ID, items=[]))


# ---------------------------------------------------------------------------
# mark_session_failed — unit
# ---------------------------------------------------------------------------

def test_mark_failed_patches_status_and_error():
    mock_http = _mock_http()
    with _patch_httpx(mock_http):
        mark_session_failed(MarkFailedInput(session_id=SESSION_ID, error="boom"))

    patch_call = mock_http.patch.call_args
    assert "/rest/v1/meeting_sessions" in patch_call.args[0]
    assert patch_call.kwargs["json"]["status"] == "failed"
    assert patch_call.kwargs["json"]["error"] == "boom"
    assert f"eq.{SESSION_ID}" in patch_call.kwargs["params"]["id"]


def test_save_does_not_write_error_field():
    """
    Successful saves must not touch the 'error' column, which stays NULL in the DB.
    If save_action_items writes error="", the frontend would see a non-null error
    on a completed session and might display it incorrectly.
    (Discovered via exploratory testing: session.error is None for completed sessions.)
    """
    mock_http = _mock_http()
    with _patch_httpx(mock_http):
        save_action_items(SaveActionItemsInput(session_id=SESSION_ID, items=ITEMS))

    patch_call = mock_http.patch.call_args
    patch_payload = patch_call.kwargs["json"]
    # The PATCH payload must not include an 'error' key
    assert "error" not in patch_payload, (
        f"save_action_items must not write the error field; got payload={patch_payload}"
    )


def test_mark_failed_propagates_supabase_error(monkeypatch):
    """If the PATCH fails, the error propagates — mark_session_failed must not swallow it."""
    mock_http = _mock_http()
    mock_http.patch.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
        "503 Service Unavailable",
        request=MagicMock(),
        response=MagicMock(status_code=503),
    )
    with _patch_httpx(mock_http):
        with pytest.raises(httpx.HTTPStatusError):
            mark_session_failed(MarkFailedInput(session_id=SESSION_ID, error="boom"))


# ---------------------------------------------------------------------------
# Integration tests — real Supabase (skip when stack not running)
# ---------------------------------------------------------------------------

def _supabase_available() -> bool:
    url = os.environ.get("SUPABASE_URL", "http://localhost:54321")
    try:
        resp = httpx.get(f"{url}/rest/v1/", timeout=2)
        return resp.status_code < 500
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not _supabase_available(), reason="Supabase not reachable")
def test_save_action_items_writes_to_real_db(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not key:
        pytest.skip("SUPABASE_SERVICE_ROLE_KEY not set")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", key)

    import uuid
    base = "http://localhost:54321"
    session_id = str(uuid.uuid4())
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    with httpx.Client() as client:
        r = client.post(
            f"{base}/rest/v1/meeting_sessions",
            json={"id": session_id, "notes": "integration test", "status": "pending"},
            headers=headers,
        )
        r.raise_for_status()

    try:
        save_action_items(SaveActionItemsInput(session_id=session_id, items=ITEMS))

        with httpx.Client() as client:
            r = client.get(
                f"{base}/rest/v1/meeting_sessions",
                params={"id": f"eq.{session_id}", "select": "status"},
                headers=headers,
            )
            assert r.json()[0]["status"] == "completed"

            r = client.get(
                f"{base}/rest/v1/action_items",
                params={"session_id": f"eq.{session_id}"},
                headers=headers,
            )
            assert len(r.json()) == 2
    finally:
        with httpx.Client() as client:
            client.delete(
                f"{base}/rest/v1/meeting_sessions",
                params={"id": f"eq.{session_id}"},
                headers=headers,
            )


@pytest.mark.integration
@pytest.mark.skipif(not _supabase_available(), reason="Supabase not reachable")
def test_mark_session_failed_writes_to_real_db(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not key:
        pytest.skip("SUPABASE_SERVICE_ROLE_KEY not set")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", key)

    import uuid
    base = "http://localhost:54321"
    session_id = str(uuid.uuid4())
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    with httpx.Client() as client:
        r = client.post(
            f"{base}/rest/v1/meeting_sessions",
            json={"id": session_id, "notes": "integration test fail", "status": "pending"},
            headers=headers,
        )
        r.raise_for_status()

    try:
        mark_session_failed(MarkFailedInput(session_id=session_id, error="test failure"))

        with httpx.Client() as client:
            r = client.get(
                f"{base}/rest/v1/meeting_sessions",
                params={"id": f"eq.{session_id}", "select": "status,error"},
                headers=headers,
            )
            row = r.json()[0]
            assert row["status"] == "failed"
            assert row["error"] == "test failure"
    finally:
        with httpx.Client() as client:
            client.delete(
                f"{base}/rest/v1/meeting_sessions",
                params={"id": f"eq.{session_id}"},
                headers=headers,
            )
