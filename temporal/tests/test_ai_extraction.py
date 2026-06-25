"""Unit tests for extract_action_items — Anthropic client is always mocked."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from src.activities.ai_extraction import extract_action_items


def _mock_response(text: str) -> MagicMock:
    content = MagicMock()
    content.text = text
    msg = MagicMock()
    msg.content = [content]
    return msg


def _patched_client(text: str):
    """Context manager: patches anthropic.Anthropic and returns the mock instance."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_response(text)
    return patch("anthropic.Anthropic", return_value=mock_client)


# ---------------------------------------------------------------------------
# Happy-path parsing
# ---------------------------------------------------------------------------

def test_extracts_three_items(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    payload = json.dumps([
        {"task": "Write tests", "owner": "Alice", "due_date": "Friday"},
        {"task": "Review PR", "owner": "Bob", "due_date": "Monday"},
        {"task": "Deploy", "owner": "Carol", "due_date": "Thursday"},
    ])
    with _patched_client(payload):
        result = extract_action_items("some meeting notes")
    assert len(result) == 3
    assert result[0] == {"task": "Write tests", "owner": "Alice", "due_date": "Friday"}
    assert result[1] == {"task": "Review PR", "owner": "Bob", "due_date": "Monday"}
    assert result[2] == {"task": "Deploy", "owner": "Carol", "due_date": "Thursday"}


def test_empty_array_returns_empty_list(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with _patched_client("[]"):
        result = extract_action_items("no action items here")
    assert result == []


# ---------------------------------------------------------------------------
# Model call verification — catches wrong model or dropped notes
# ---------------------------------------------------------------------------

def test_correct_model_is_used(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_response("[]")
    with patch("anthropic.Anthropic", return_value=mock_client):
        extract_action_items("notes")
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


def test_notes_are_embedded_in_prompt(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    notes_text = "UNIQUE_MARKER_STRING"
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_response("[]")
    with patch("anthropic.Anthropic", return_value=mock_client):
        extract_action_items(notes_text)
    call_kwargs = mock_client.messages.create.call_args.kwargs
    prompt_content = call_kwargs["messages"][0]["content"]
    assert notes_text in prompt_content, "Meeting notes must be passed to the model prompt"


# ---------------------------------------------------------------------------
# Default-value normalisation
# ---------------------------------------------------------------------------

def test_missing_owner_defaults_to_unassigned(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    payload = json.dumps([{"task": "Fix bug"}])
    with _patched_client(payload):
        result = extract_action_items("notes")
    assert result[0]["owner"] == "Unassigned"


def test_null_owner_defaults_to_unassigned(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    payload = json.dumps([{"task": "Fix bug", "owner": None, "due_date": "Tomorrow"}])
    with _patched_client(payload):
        result = extract_action_items("notes")
    assert result[0]["owner"] == "Unassigned"


def test_missing_due_date_defaults_to_no_date(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    payload = json.dumps([{"task": "Fix bug", "owner": "Alice"}])
    with _patched_client(payload):
        result = extract_action_items("notes")
    assert result[0]["due_date"] == "No date"


def test_empty_due_date_defaults_to_no_date(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    payload = json.dumps([{"task": "Fix bug", "owner": "Alice", "due_date": ""}])
    with _patched_client(payload):
        result = extract_action_items("notes")
    assert result[0]["due_date"] == "No date"


# ---------------------------------------------------------------------------
# Malformed model output
# ---------------------------------------------------------------------------

def test_malformed_json_returns_empty_list(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with _patched_client("Sorry, I cannot help with that."):
        result = extract_action_items("notes")
    assert result == []


def test_json_array_embedded_in_prose(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    prose = 'Here are the items: [{"task": "Deploy", "owner": "Alice", "due_date": "Friday"}] Done.'
    with _patched_client(prose):
        result = extract_action_items("notes")
    assert len(result) == 1
    assert result[0]["task"] == "Deploy"


def test_non_list_response_returns_empty(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with _patched_client('{"task": "only one"}'):
        result = extract_action_items("notes")
    assert result == []


def test_items_without_task_field_are_skipped(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    payload = json.dumps([
        {"owner": "Alice", "due_date": "Friday"},
        {"task": "Valid task", "owner": "Bob", "due_date": "Monday"},
    ])
    with _patched_client(payload):
        result = extract_action_items("notes")
    assert len(result) == 1
    assert result[0]["task"] == "Valid task"


# ---------------------------------------------------------------------------
# API key validation — all forms of missing/empty key must raise
# ---------------------------------------------------------------------------

def test_missing_api_key_raises_application_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ApplicationError) as exc_info:
        extract_action_items("notes")
    assert exc_info.value.non_retryable is True


def test_empty_string_api_key_raises_application_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with pytest.raises(ApplicationError) as exc_info:
        extract_action_items("notes")
    assert exc_info.value.non_retryable is True


def test_whitespace_only_api_key_raises_application_error(monkeypatch):
    """Key strips to empty — must be treated the same as missing."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    with pytest.raises(ApplicationError) as exc_info:
        extract_action_items("notes")
    assert exc_info.value.non_retryable is True
