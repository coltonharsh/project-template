-- Meeting notes extraction: session tracker + action items output

CREATE TABLE meeting_sessions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    notes       text NOT NULL,
    workflow_id text,
    status      text NOT NULL DEFAULT 'pending',  -- pending | completed | failed
    error       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION set_timestamp_meeting_sessions()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_timestamp_meeting_sessions_trg
BEFORE UPDATE ON meeting_sessions
FOR EACH ROW EXECUTE FUNCTION set_timestamp_meeting_sessions();

CREATE TABLE action_items (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  uuid NOT NULL REFERENCES meeting_sessions(id) ON DELETE CASCADE,
    task        text NOT NULL,
    owner       text NOT NULL DEFAULT 'Unassigned',
    due_date    text NOT NULL DEFAULT 'No date',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_action_items_session_id ON action_items (session_id);

GRANT ALL ON meeting_sessions TO anon, authenticated, service_role;
GRANT ALL ON action_items TO anon, authenticated, service_role;
