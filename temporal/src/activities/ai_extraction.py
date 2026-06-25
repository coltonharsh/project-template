from __future__ import annotations

import json
import logging
import os
import re

from temporalio import activity
from temporalio.exceptions import ApplicationError

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
Extract all action items from the following meeting notes.
Return ONLY a valid JSON array. Each element must have exactly these three fields:
- "task": string describing what needs to be done
- "owner": name of the person responsible, or "Unassigned" if not mentioned
- "due_date": the due date or deadline as a string, or "No date" if not mentioned

If there are no action items, return an empty array: []

Meeting notes:
{notes}

Respond with only the JSON array. No explanation, no markdown, no code fences.\
"""


@activity.defn
def extract_action_items(notes: str) -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ApplicationError(
            "ANTHROPIC_API_KEY is not set — cannot call model",
            non_retryable=True,
        )

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(notes=notes)}],
    )

    text = message.content[0].text.strip()
    logger.info("Model response received", extra={"length": len(text)})

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        # Model may have wrapped the array in explanation text; try to extract it
        match = re.search(r"\[.*?\]", text, re.DOTALL)
        if match:
            try:
                items = json.loads(match.group())
            except json.JSONDecodeError:
                items = []
        else:
            logger.warning("Could not parse JSON from model response", extra={"text": text[:200]})
            items = []

    if not isinstance(items, list):
        items = []

    return [
        {
            "task": str(item.get("task", "")).strip(),
            "owner": str(item.get("owner") or "Unassigned").strip() or "Unassigned",
            "due_date": str(item.get("due_date") or "No date").strip() or "No date",
        }
        for item in items
        if isinstance(item, dict) and item.get("task")
    ]
