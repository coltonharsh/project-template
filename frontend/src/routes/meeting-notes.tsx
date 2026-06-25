import { createFileRoute } from '@tanstack/react-router';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/data/supabase';

export const Route = createFileRoute('/meeting-notes')({
  component: MeetingNotesPage,
});

const OPS_API_URL = (import.meta.env.VITE_OPS_API_URL as string) || 'http://localhost:8000';

type Session = {
  id: string;
  notes: string;
  workflow_id: string | null;
  status: 'pending' | 'completed' | 'failed';
  error: string | null;
  created_at: string;
};

type ActionItem = {
  id: string;
  session_id: string;
  task: string;
  owner: string;
  due_date: string;
};

async function submitNotes(notes: string): Promise<{ session_id: string; workflow_id: string }> {
  const res = await fetch(`${OPS_API_URL}/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Could not reach ops-api' }));
    throw new Error(err.detail || 'Extraction failed');
  }
  return res.json();
}

function StatusDot({ status }: { status: Session['status'] }) {
  const color =
    status === 'completed' ? 'bg-green-500' :
    status === 'failed'    ? 'bg-red-500'   : 'bg-yellow-400 animate-pulse';
  return <span className={`inline-block w-2 h-2 rounded-full ${color}`} />;
}

export function MeetingNotesPage() {
  const [notes, setNotes] = useState('');
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const submitMutation = useMutation({
    mutationFn: submitNotes,
    onSuccess: (data) => {
      setCurrentSessionId(data.session_id);
      setNotes('');
      queryClient.invalidateQueries({ queryKey: ['all-sessions'] });
    },
  });

  // Poll the current session until it leaves 'pending'
  const sessionQuery = useQuery({
    queryKey: ['meeting-session', currentSessionId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('meeting_sessions')
        .select('*')
        .eq('id', currentSessionId!)
        .single();
      if (error) throw error;
      return data as Session;
    },
    enabled: !!currentSessionId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return !status || status === 'pending' ? 2000 : false;
    },
  });

  // Fetch action items once session is complete
  const itemsQuery = useQuery({
    queryKey: ['action-items', currentSessionId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('action_items')
        .select('*')
        .eq('session_id', currentSessionId!)
        .order('created_at');
      if (error) throw error;
      return data as ActionItem[];
    },
    enabled: sessionQuery.data?.status === 'completed',
  });

  // All past sessions for the history list
  const allSessionsQuery = useQuery({
    queryKey: ['all-sessions'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('meeting_sessions')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(10);
      if (error) throw error;
      return data as Session[];
    },
  });

  const isProcessing =
    submitMutation.isPending || sessionQuery.data?.status === 'pending';
  const sessionStatus = sessionQuery.data?.status;

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Meeting Notes → Action Items</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Paste meeting notes and the AI will extract action items with owners and due dates via a
          Temporal workflow.
        </p>
      </div>

      {/* Input form */}
      <div className="space-y-3">
        <textarea
          className="w-full min-h-[160px] rounded-lg border bg-card p-3 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder="Paste your meeting notes here..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          disabled={isProcessing}
        />
        <button
          onClick={() => submitMutation.mutate(notes)}
          disabled={!notes.trim() || isProcessing}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50 hover:bg-primary/90 transition-colors"
        >
          {isProcessing ? 'Processing…' : 'Extract Action Items'}
        </button>

        {submitMutation.isError && (
          <p className="text-sm text-destructive">
            Error: {(submitMutation.error as Error).message}
          </p>
        )}

        {isProcessing && currentSessionId && (
          <p className="text-sm text-muted-foreground">
            Running Temporal workflow…{' '}
            <a
              href="http://localhost:8080"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              Watch it in the Temporal UI
            </a>
          </p>
        )}
      </div>

      {/* Error state */}
      {sessionStatus === 'failed' && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          <strong>Extraction failed:</strong>{' '}
          {sessionQuery.data?.error || 'An unknown error occurred.'}
        </div>
      )}

      {/* Results */}
      {sessionStatus === 'completed' && (
        <div className="space-y-3">
          <h2 className="text-base font-semibold">Extracted Action Items</h2>

          {itemsQuery.isLoading && (
            <p className="text-sm text-muted-foreground">Loading…</p>
          )}

          {itemsQuery.data?.length === 0 && (
            <div className="rounded-lg border border-border bg-muted/30 px-5 py-4 space-y-1">
              <p className="text-sm font-medium text-foreground">No follow-ups detected</p>
              <p className="text-sm text-muted-foreground">
                No action items were found in these notes. Try including who is doing
                what and by when — for example:{' '}
                <span className="italic">"Alice will fix the login bug by Friday."</span>
              </p>
            </div>
          )}

          {itemsQuery.data && itemsQuery.data.length > 0 && (
            <div className="rounded-lg border overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium">Task</th>
                    <th className="text-left px-4 py-2 font-medium w-32">Owner</th>
                    <th className="text-left px-4 py-2 font-medium w-28">Due Date</th>
                  </tr>
                </thead>
                <tbody>
                  {itemsQuery.data.map((item, i) => (
                    <tr key={item.id} className={i % 2 === 0 ? '' : 'bg-muted/20'}>
                      <td className="px-4 py-2">{item.task}</td>
                      <td className="px-4 py-2 text-muted-foreground">{item.owner}</td>
                      <td className="px-4 py-2 text-muted-foreground">{item.due_date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Past sessions */}
      {allSessionsQuery.data && allSessionsQuery.data.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-base font-semibold text-muted-foreground">Past Submissions</h2>
          <div className="space-y-1">
            {allSessionsQuery.data.map((s) => (
              <button
                key={s.id}
                onClick={() => setCurrentSessionId(s.id)}
                className="w-full text-left rounded-lg border px-4 py-2 text-sm hover:bg-muted transition-colors flex items-center gap-2"
              >
                <StatusDot status={s.status} />
                <span className="flex-1 truncate">
                  {s.notes.slice(0, 70)}{s.notes.length > 70 ? '…' : ''}
                </span>
                <span className="text-muted-foreground shrink-0">
                  {new Date(s.created_at).toLocaleTimeString()}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
