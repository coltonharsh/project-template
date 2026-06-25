"""
Unit tests for MeetingNotesWorkflow using Temporal's in-process test environment.
No real Temporal server, no real Anthropic API, no real Supabase.
"""
from __future__ import annotations

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.activities.meeting_notes import MarkFailedInput, SaveActionItemsInput
from src.workflows.meeting_notes.meeting_notes_workflow import (
    MeetingNotesInput,
    MeetingNotesWorkflow,
)

TASK_QUEUE = "test-meeting-notes"

# ---------------------------------------------------------------------------
# Module-level capture lists — reset before each test by the autouse fixture
# ---------------------------------------------------------------------------

_saved: list[SaveActionItemsInput] = []
_failed: list[MarkFailedInput] = []


# ---------------------------------------------------------------------------
# Mock activities — registered by name so the workflow can dispatch to them
# ---------------------------------------------------------------------------

@activity.defn(name="extract_action_items")
async def mock_extract(notes: str) -> list[dict]:
    return [
        {"task": "Fix login bug", "owner": "Alice", "due_date": "Friday"},
        {"task": "Write docs", "owner": "Bob", "due_date": "No date"},
    ]


@activity.defn(name="extract_action_items")
async def mock_extract_empty(notes: str) -> list[dict]:
    return []


@activity.defn(name="extract_action_items")
async def mock_extract_fails(notes: str) -> list[dict]:
    raise ApplicationError("Model unavailable", non_retryable=True)


@activity.defn(name="save_action_items")
async def mock_save(inp: SaveActionItemsInput) -> None:
    _saved.append(inp)


@activity.defn(name="save_action_items")
async def mock_save_raises(inp: SaveActionItemsInput) -> None:
    raise ApplicationError("Supabase unreachable", non_retryable=True)


@activity.defn(name="mark_session_failed")
async def mock_mark_failed(inp: MarkFailedInput) -> None:
    _failed.append(inp)


@activity.defn(name="mark_session_failed")
async def mock_mark_failed_also_raises(inp: MarkFailedInput) -> None:
    """Simulates mark_session_failed itself failing — the workflow must swallow it."""
    _failed.append(inp)
    raise ApplicationError("DB also down", non_retryable=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_capture():
    _saved.clear()
    _failed.clear()
    yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_happy_path_returns_correct_item_count():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MeetingNotesWorkflow],
            activities=[mock_extract, mock_save, mock_mark_failed],
        ):
            result = await env.client.execute_workflow(
                MeetingNotesWorkflow.run,
                MeetingNotesInput(session_id="s-happy", notes="Team sync notes"),
                id="wf-happy",
                task_queue=TASK_QUEUE,
            )

    assert result.session_id == "s-happy"
    assert result.item_count == 2
    assert len(_saved) == 1
    assert _saved[0].session_id == "s-happy"
    assert len(_saved[0].items) == 2
    assert len(_failed) == 0


async def test_empty_extraction_still_completes():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MeetingNotesWorkflow],
            activities=[mock_extract_empty, mock_save, mock_mark_failed],
        ):
            result = await env.client.execute_workflow(
                MeetingNotesWorkflow.run,
                MeetingNotesInput(session_id="s-empty", notes="Nothing to extract"),
                id="wf-empty",
                task_queue=TASK_QUEUE,
            )

    assert result.item_count == 0
    assert len(_saved) == 1
    assert _saved[0].items == []
    assert len(_failed) == 0


async def test_extraction_failure_calls_mark_failed_and_reraises():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MeetingNotesWorkflow],
            activities=[mock_extract_fails, mock_save, mock_mark_failed],
        ):
            with pytest.raises(WorkflowFailureError):
                await env.client.execute_workflow(
                    MeetingNotesWorkflow.run,
                    MeetingNotesInput(session_id="s-fail", notes="bad notes"),
                    id="wf-fail",
                    task_queue=TASK_QUEUE,
                )

    assert len(_failed) == 1
    assert _failed[0].session_id == "s-fail"
    # The error string must be non-empty; Temporal wraps the original in ActivityError
    assert isinstance(_failed[0].error, str) and len(_failed[0].error) > 0
    assert len(_saved) == 0


async def test_save_failure_calls_mark_failed_and_reraises():
    """save_action_items failure is caught by the same try/except — mark_failed must be called."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MeetingNotesWorkflow],
            activities=[mock_extract, mock_save_raises, mock_mark_failed],
        ):
            with pytest.raises(WorkflowFailureError):
                await env.client.execute_workflow(
                    MeetingNotesWorkflow.run,
                    MeetingNotesInput(session_id="s-save-fail", notes="notes"),
                    id="wf-save-fail",
                    task_queue=TASK_QUEUE,
                )

    assert len(_failed) == 1
    assert _failed[0].session_id == "s-save-fail"
    # save raised before appending — _saved must be empty
    assert len(_saved) == 0


async def test_mark_failed_failure_is_swallowed_and_original_error_propagates():
    """
    The workflow's inner try/except around mark_session_failed must swallow that failure
    and re-raise the original exception — not the mark_failed exception.
    """
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MeetingNotesWorkflow],
            activities=[mock_extract_fails, mock_save, mock_mark_failed_also_raises],
        ):
            with pytest.raises(WorkflowFailureError):
                await env.client.execute_workflow(
                    MeetingNotesWorkflow.run,
                    MeetingNotesInput(session_id="s-double-fail", notes="bad"),
                    id="wf-double-fail",
                    task_queue=TASK_QUEUE,
                )

    # mark_failed was invoked (and failed), but the workflow still propagated
    assert len(_failed) == 1
    assert _failed[0].session_id == "s-double-fail"
