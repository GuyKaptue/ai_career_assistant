import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import Sidebar, { groupSessionsByTime } from './Sidebar';
import { I18nProvider } from '../../i18n/index.jsx';

function renderSidebar(props = {}) {
  const handlers = {
    onSelectSession: vi.fn(),
    onNewChat: vi.fn(),
    onOpenProject: vi.fn(),
    onDeleteSession: vi.fn(),
    onCloseMobileSidebar: vi.fn(),
    ...props,
  };
  render(
    <I18nProvider>
      <Sidebar {...handlers} />
    </I18nProvider>,
  );
  return handlers;
}

describe('Sidebar projects', () => {
  it('renders every project tile as an actionable button', () => {
    renderSidebar();

    const tiles = screen.getAllByRole('button', { pressed: false });
    const projectButtons = tiles.filter((btn) =>
      ['Career Coaching', 'Resume Review', 'Interview Prep', 'Job Search'].some((label) =>
        btn.textContent.includes(label),
      ),
    );

    expect(projectButtons).toHaveLength(4);
  });

  it('clicking a project tile calls onOpenProject with its mode', () => {
    const handlers = renderSidebar();

    fireEvent.click(screen.getByTitle(/Resume Review/));

    expect(handlers.onOpenProject).toHaveBeenCalledTimes(1);
    expect(handlers.onOpenProject).toHaveBeenCalledWith(
      expect.objectContaining({ key: 'resumeReview', mode: 'ats_checker' }),
    );
  });

  it('clicking a project tile closes the mobile drawer', () => {
    const handlers = renderSidebar();

    fireEvent.click(screen.getByTitle(/Job Search/));

    expect(handlers.onCloseMobileSidebar).toHaveBeenCalledTimes(1);
  });

  it('marks the tile matching the open session mode as pressed', () => {
    renderSidebar({
      activeSessionId: 's1',
      sessions: [{ id: 's1', title: 'Prep chat', mode: 'interview_prep', updated_at: new Date().toISOString() }],
    });

    expect(screen.getByTitle(/Interview Prep/)).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTitle(/Job Search/)).toHaveAttribute('aria-pressed', 'false');
  });

  it('selecting a session notifies the parent and closes the drawer', () => {
    const now = new Date().toISOString();
    const handlers = renderSidebar({
      activeSessionId: 's2',
      sessions: [
        { id: 's1', title: 'First chat', mode: 'general', updated_at: now },
        { id: 's2', title: 'Second chat', mode: 'general', updated_at: now },
      ],
    });

    fireEvent.click(screen.getByText('First chat'));

    expect(handlers.onSelectSession).toHaveBeenCalledWith('s1');
    expect(handlers.onCloseMobileSidebar).toHaveBeenCalled();
  });

  it('filters the session list from the search query', () => {
    const now = new Date().toISOString();
    renderSidebar({
      sessions: [
        { id: 's1', title: 'Berlin CV review', mode: 'general', updated_at: now },
        { id: 's2', title: 'Munich cover letter', mode: 'cover_letter', updated_at: now },
      ],
      searchQuery: 'munich',
    });

    expect(screen.getByText('Munich cover letter')).toBeInTheDocument();
    expect(screen.queryByText('Berlin CV review')).not.toBeInTheDocument();
  });

  it('shows an empty state when there are no sessions', () => {
    renderSidebar({ sessions: [] });

    expect(screen.getByText('No conversations yet')).toBeInTheDocument();
  });
});

describe('groupSessionsByTime', () => {
  const at = (iso) => ({ id: iso, title: iso, updated_at: iso });
  const now = new Date('2026-10-10T12:00:00Z');

  it('buckets sessions into today, yesterday, previous 7 days and older', () => {
    const buckets = groupSessionsByTime(
      [
        at('2026-10-10T09:00:00Z'),
        at('2026-10-09T09:00:00Z'),
        at('2026-10-06T09:00:00Z'),
        at('2026-09-01T09:00:00Z'),
      ],
      now,
    );

    expect(buckets.today.map((s) => s.id)).toEqual(['2026-10-10T09:00:00Z']);
    expect(buckets.yesterday.map((s) => s.id)).toEqual(['2026-10-09T09:00:00Z']);
    expect(buckets.previous7Days.map((s) => s.id)).toEqual(['2026-10-06T09:00:00Z']);
    expect(buckets.older.map((s) => s.id)).toEqual(['2026-09-01T09:00:00Z']);
  });

  it('sends unparsable timestamps to the older bucket', () => {
    const buckets = groupSessionsByTime([at('not-a-date')], now);
    expect(buckets.older).toHaveLength(1);
  });
});
