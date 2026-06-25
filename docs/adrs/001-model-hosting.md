# ADR-001: Model Hosting — Anthropic SDK as Local Fallback

## Status
**Accepted** — 2026-06-24

## Context

### Background
The Meeting Notes → Action Items feature requires an AI model call to extract structured data from free-text. The Day 2 brief specified AWS Bedrock or Azure OpenAI as the target model endpoints, reflecting team infrastructure where credentials are managed centrally via IAM roles.

### Problem Statement
The model call must happen inside a Temporal activity (not the frontend) so it is retryable, observable, and swappable without touching the UI. The question is which provider to use and where to keep the credentials.

### Constraints
- Must work locally with `make up` and no additional infrastructure
- API key must not be hardcoded; must come from environment variables
- No team Bedrock or Azure endpoint is available for this local workshop build

## Decision
Use the **Anthropic Python SDK** with the direct Anthropic API as the model provider for this local build.

### Proposed Solution
- Add `anthropic` as a dependency in `temporal/pyproject.toml`
- Read `ANTHROPIC_API_KEY` from the worker container's environment at activity execution time
- If the key is missing, raise a `non_retryable` `ApplicationError` immediately — the error surfaces through the workflow and is written to the session's `error` field so the frontend can display it clearly
- Model: `claude-haiku-4-5-20251001` (fast, cheap, well-suited for structured extraction)

### Alternatives Considered

#### Alternative 1: AWS Bedrock
**Description**: Call Claude via `boto3` using a Bedrock endpoint with IAM credentials

**Pros**:
- Team-managed credentials via IAM roles — no developer holds a personal key
- No per-request cost difference (same model, different billing)
- Preferred path for production per the brief

**Cons**:
- Requires `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` in the Docker container
- No team Bedrock endpoint available for this workshop

**Why not chosen**: No access to team Bedrock endpoint in this local workshop environment.

#### Alternative 2: Azure OpenAI
**Description**: Call a GPT-4o or similar model via Azure OpenAI Service

**Pros**:
- Enterprise billing and compliance via Azure subscription
- Preferred path for Microsoft-aligned teams

**Cons**:
- Requires Azure endpoint URL + API key + deployment name
- No team Azure endpoint available for this workshop
- Adds `openai` SDK dependency

**Why not chosen**: No access to team Azure endpoint in this local workshop environment.

#### Alternative 3: Model call in a Supabase Edge Function
**Description**: Put the AI call in a Deno Edge Function triggered by a database insert

**Pros**:
- No ops-api needed; fewer moving parts

**Cons**:
- Violates the spec requirement that the model call happens inside a Temporal activity
- Loses Temporal's retry, observability, and timeout guarantees

**Why not chosen**: Contradicts the core architectural requirement.

## Consequences

### Positive Consequences
- Works immediately with a single `ANTHROPIC_API_KEY` env var — no infrastructure setup
- Model call is isolated inside `extract_action_items` activity in `temporal/src/activities/ai_extraction.py`
- Frontend, ops-api, and workflow structure are completely provider-agnostic

### Negative Consequences
- Each developer holds a personal API key rather than using shared team credentials
- Anthropic API has rate limits that differ from Bedrock

### Migration Path to Production (Bedrock or Azure)
Only one file changes: `temporal/src/activities/ai_extraction.py`

**To swap to Bedrock:**
1. Replace `anthropic` with `boto3` in `temporal/pyproject.toml`
2. In `extract_action_items`: replace the Anthropic client call with a `boto3` Bedrock client call
3. Replace env var `ANTHROPIC_API_KEY` with `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`

The frontend, ops-api, workflow, and database schema are unchanged.

## Validation

### Success Criteria
- `ANTHROPIC_API_KEY` missing → clear error in UI (not a silent failure)
- Valid key → extraction completes within 30 seconds end-to-end
- Workflow visible in Temporal UI at localhost:8080
- Results persisted in Supabase and visible after page refresh

## Metadata
- **Date**: 2026-06-24
- **Author**: Colton Harsh
- **Tags**: [ai, model-hosting, temporal, architecture]
