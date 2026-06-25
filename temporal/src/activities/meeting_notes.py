from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from temporalio import activity

logger = logging.getLogger(__name__)


@dataclass
class SaveActionItemsInput:
    session_id: str
    items: list[dict]


@dataclass
class MarkFailedInput:
    session_id: str
    error: str


def _base_url() -> str:
    return os.environ.get("SUPABASE_URL", "http://host.docker.internal:54321")


def _headers() -> dict:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


@activity.defn
def save_action_items(input: SaveActionItemsInput) -> None:
    import httpx

    base = _base_url()
    headers = _headers()

    with httpx.Client() as client:
        if input.items:
            rows = [
                {
                    "session_id": input.session_id,
                    "task": item.get("task", ""),
                    "owner": item.get("owner") or "Unassigned",
                    "due_date": item.get("due_date") or "No date",
                }
                for item in input.items
            ]
            resp = client.post(f"{base}/rest/v1/action_items", json=rows, headers=headers)
            resp.raise_for_status()

        resp = client.patch(
            f"{base}/rest/v1/meeting_sessions",
            json={"status": "completed"},
            headers=headers,
            params={"id": f"eq.{input.session_id}"},
        )
        resp.raise_for_status()

    logger.info("save_action_items done", extra={"session_id": input.session_id, "count": len(input.items)})


@activity.defn
def mark_session_failed(input: MarkFailedInput) -> None:
    import httpx

    base = _base_url()
    headers = _headers()

    with httpx.Client() as client:
        resp = client.patch(
            f"{base}/rest/v1/meeting_sessions",
            json={"status": "failed", "error": input.error},
            headers=headers,
            params={"id": f"eq.{input.session_id}"},
        )
        resp.raise_for_status()

    logger.info("mark_session_failed done", extra={"session_id": input.session_id})
