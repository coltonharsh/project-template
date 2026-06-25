/**
 * Unit tests for the Meeting Notes page empty-state block.
 * All queries and mutations are mocked — no network calls.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@tanstack/react-router', () => ({
  createFileRoute: () => (config: Record<string, unknown>) => config,
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(),
  useMutation: vi.fn(),
  useQueryClient: vi.fn(),
}))

vi.mock('@/data/supabase', () => ({
  supabase: {},
}))

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { MeetingNotesPage } from '../meeting-notes'

type ActionItem = {
  id: string
  session_id: string
  task: string
  owner: string
  due_date: string
}

function mockQueries({
  sessionStatus = 'completed' as 'pending' | 'completed' | 'failed',
  items = [] as ActionItem[],
  itemsLoading = false,
} = {}) {
  // useQuery is called in this exact component order — positional dependency is intentional.
  // If a new useQuery call is added to the component before itemsQuery, these tests will
  // break loudly (wrong data fed to wrong query) rather than silently passing.
  //   1st call → sessionQuery   (queryKey: ['meeting-session', sessionId])
  //   2nd call → itemsQuery     (queryKey: ['action-items', sessionId])
  //   3rd call → allSessionsQuery (queryKey: ['all-sessions'])
  // The enabled: false flags on sessionQuery/itemsQuery are ignored by vi.fn().
  vi.mocked(useQuery)
    .mockReturnValueOnce({ data: { status: sessionStatus }, isLoading: false, error: null } as never)
    .mockReturnValueOnce({ data: itemsLoading ? undefined : items, isLoading: itemsLoading, error: null } as never)
    .mockReturnValueOnce({ data: [], isLoading: false, error: null } as never)

  vi.mocked(useMutation).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  } as never)

  vi.mocked(useQueryClient).mockReturnValue({
    invalidateQueries: vi.fn(),
  } as never)
}

describe('MeetingNotesPage — empty state', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('T1: renders "No follow-ups detected" heading when items query returns empty array', () => {
    mockQueries({ items: [] })
    render(<MeetingNotesPage />)
    expect(screen.getByText('No follow-ups detected')).toBeInTheDocument()
  })

  it('T2: renders the guidance sentence and example phrase inside the same container', () => {
    mockQueries({ items: [] })
    render(<MeetingNotesPage />)
    // Use within() to verify both pieces of copy are siblings inside the same box —
    // guards against one of them appearing in an unrelated part of the page.
    const heading = screen.getByText('No follow-ups detected')
    const container = heading.closest('div')!
    expect(within(container).getByText(/No action items were found in these notes/)).toBeInTheDocument()
    expect(within(container).getByText(/"Alice will fix the login bug by Friday\./)).toBeInTheDocument()
  })

  it('T3: does not render the empty state when items exist — and the items table does', () => {
    mockQueries({
      items: [{ id: '1', session_id: 's1', task: 'Fix bug', owner: 'Alice', due_date: 'Friday' }],
    })
    render(<MeetingNotesPage />)
    expect(screen.queryByText('No follow-ups detected')).not.toBeInTheDocument()
    // Positive assertion: confirms results block rendered normally, not just that it was removed
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('Fix bug')).toBeInTheDocument()
  })

  it('T4: does not render the old one-liner copy', () => {
    mockQueries({ items: [] })
    render(<MeetingNotesPage />)
    expect(
      screen.queryByText('No action items found in these notes.'),
    ).not.toBeInTheDocument()
  })

  it('T5: does not render the empty state while items are loading — shows spinner instead', () => {
    mockQueries({ itemsLoading: true })
    render(<MeetingNotesPage />)
    // Positive assertion: confirms we're in the loading path, not just a non-completed session
    expect(screen.getByText('Loading…')).toBeInTheDocument()
    expect(screen.queryByText('No follow-ups detected')).not.toBeInTheDocument()
  })
})
