from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from temporalio.client import Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "temporal:7233")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://host.docker.internal:54321")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_temporal_client: Client | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _temporal_client
    logger.info("Connecting to Temporal", extra={"address": TEMPORAL_ADDRESS})
    _temporal_client = await Client.connect(TEMPORAL_ADDRESS)
    logger.info("Temporal client ready")
    yield


app = FastAPI(title="Ops API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Must match MeetingNotesInput dataclass in the worker
@dataclass
class MeetingNotesInput:
    session_id: str
    notes: str


class ExtractRequest(BaseModel):
    notes: str


def _supabase_headers(prefer: str = "return=minimal") -> dict:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


@app.get("/healthz")
async def health():
    return {"status": "ok"}


@app.post("/extract")
async def extract(req: ExtractRequest):
    if not req.notes.strip():
        raise HTTPException(status_code=400, detail="Notes cannot be empty")

    session_id = str(uuid.uuid4())

    # Create the session row so the frontend can poll it immediately
    with httpx.Client() as http:
        resp = http.post(
            f"{SUPABASE_URL}/rest/v1/meeting_sessions",
            json={"id": session_id, "notes": req.notes, "status": "pending"},
            headers=_supabase_headers(),
        )
        if resp.status_code not in (200, 201):
            logger.error("Failed to create session", extra={"status": resp.status_code, "body": resp.text})
            raise HTTPException(status_code=500, detail="Failed to create session in database")

    # Start the Temporal workflow
    handle = await _temporal_client.start_workflow(
        "MeetingNotesWorkflow",
        MeetingNotesInput(session_id=session_id, notes=req.notes),
        id=f"meeting-notes-{session_id}",
        task_queue="main",
    )
    logger.info("Workflow started", extra={"workflow_id": handle.id, "session_id": session_id})

    # Stamp the workflow_id on the session (best-effort)
    with httpx.Client() as http:
        http.patch(
            f"{SUPABASE_URL}/rest/v1/meeting_sessions",
            json={"workflow_id": handle.id},
            headers=_supabase_headers(),
            params={"id": f"eq.{session_id}"},
        )

    return {"session_id": session_id, "workflow_id": handle.id}
