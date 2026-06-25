from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ...activities.ai_extraction import extract_action_items
    from ...activities.meeting_notes import (
        MarkFailedInput,
        SaveActionItemsInput,
        mark_session_failed,
        save_action_items,
    )


@dataclass
class MeetingNotesInput:
    session_id: str
    notes: str


@dataclass
class MeetingNotesResult:
    session_id: str
    item_count: int


@workflow.defn
class MeetingNotesWorkflow:
    @workflow.run
    async def run(self, input: MeetingNotesInput) -> MeetingNotesResult:
        try:
            items: list[dict] = await workflow.execute_activity(
                extract_action_items,
                input.notes,
                start_to_close_timeout=timedelta(seconds=60),
            )
            await workflow.execute_activity(
                save_action_items,
                SaveActionItemsInput(session_id=input.session_id, items=items),
                start_to_close_timeout=timedelta(seconds=30),
            )
            return MeetingNotesResult(session_id=input.session_id, item_count=len(items))
        except Exception as e:
            try:
                await workflow.execute_activity(
                    mark_session_failed,
                    MarkFailedInput(session_id=input.session_id, error=str(e)),
                    start_to_close_timeout=timedelta(seconds=30),
                )
            except Exception:
                pass  # Best-effort; don't mask the original error
            raise
