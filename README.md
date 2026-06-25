# Boilerplate Stack

A full-stack local development environment: Supabase (Postgres + Auth + Storage), Temporal (durable workflows), a FastAPI ops-api, and a React/Vite frontend.

## Prerequisites

- Docker Desktop with Compose v2
- `make` (macOS: `xcode-select --install`)
- [Supabase CLI](https://supabase.com/docs/guides/cli) — `make up` calls `supabase start`
- Node 18+ (only needed to run the frontend outside Docker)
- An [Anthropic API key](https://console.anthropic.com) — required for the Meeting Notes feature

## Quick Start

```bash
# 1. Copy environment defaults (fill in ANTHROPIC_API_KEY)
cp .env.example .env

# 2. Start the full stack
make up
```

`make up` runs `supabase start` (Postgres + API + Auth + Studio, migrations and seed applied), then brings up Temporal, the temporal worker, the ops-api, and the frontend dev server via Docker Compose.

### Services

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Temporal UI | http://localhost:8080 |
| Supabase Studio | http://localhost:54323 |
| Supabase API | http://localhost:54321 |
| ops-api | http://localhost:8000 |

### Common commands

```bash
make down           # stop containers + Supabase
make reset          # full wipe and restart (re-applies migrations and seed)
make logs           # stream all logs
make logs-temporal  # Temporal server + worker logs
make logs-frontend  # frontend dev server logs
make supabase-status  # show Supabase URLs and local API keys
```

## Meeting Notes → Action Items

The primary demo feature. Paste raw meeting notes into the UI; the app extracts structured action items (task, owner, due date) using Claude via a Temporal workflow.

### How to demo

1. Run `make up`
2. Open http://localhost:3000/meeting-notes
3. Paste meeting notes that include owners and deadlines, for example:

   > Alice will fix the login bug by Friday.
   > Bob needs to review the PR before end of week.
   > Carol will deploy to staging by Thursday.

4. Click **Extract Action Items** — a Temporal workflow starts, calls Claude, and writes results to Supabase
5. The page polls automatically; results appear as a table within a few seconds
6. Click any past submission in the history list to reload its results

### Requirements

- `ANTHROPIC_API_KEY` must be set in `.env` (get one at https://console.anthropic.com)
- The full stack must be running (`make up`)
- The Temporal worker processes extraction on the `main` task queue

### Architecture

```
Browser → ops-api (FastAPI :8000) → Temporal workflow → Anthropic API (Claude Haiku)
                                 ↘ Supabase (session row, action items)
Browser ←─────────── polls Supabase ───────────────────────────────────────────
```

## What's Included

- **Supabase** — local Postgres + API + Auth + Storage + Studio via the Supabase CLI; migrations and seed applied on `make up`
- **Temporal** — durable workflow server + UI; worker runs `MeetingNotesWorkflow`
- **ops-api** — FastAPI service that receives frontend requests and starts Temporal workflows
- **Frontend** — React + Vite + TanStack Router + TanStack Query; polls Supabase for live session state
- **Docker Compose** — `docker-compose.yml` for the full stack; `docker-compose.dev.yml` adds live-reload mounts

## Notes

- Supabase runs via the CLI (`supabase start`), not Docker Compose. The Temporal worker reaches it at `host.docker.internal:54321`; the browser at `localhost:54321`.
- The Python services (`temporal/`, `ops-api/`) require **Python 3.11–3.13**. Python 3.14 is not yet compatible with `pydantic-core` binary wheels.
- `make up` injects Supabase auth keys automatically — you do not need to fill in `SUPABASE_ANON_KEY` or `SUPABASE_SERVICE_ROLE_KEY` in `.env` unless running `docker compose up` directly.
