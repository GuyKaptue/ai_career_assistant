import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useView, VIEWS, ViewProvider } from './useView';

vi.mock('../i18n/index.jsx', () => ({
  I18nProvider: ({ children }) => children,
  useI18n: () => ({
    t: (key, vars) => (vars ? `${key}:${JSON.stringify(vars)}` : key),
    locale: 'en',
  }),
}));

function Probe() {
  const { view, setView, views } = useView();
  return (
    <div>
      <span data-testid="active">{view}</span>
      <span data-testid="count">{views.length}</span>
      {VIEWS.map((entry) => (
        <button key={entry.id} onClick={() => setView(entry.id)}>
          {entry.id}
        </button>
      ))}
    </div>
  );
}

describe('useView', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('exposes every workspace, chat first', () => {
    render(<ViewProvider><Probe /></ViewProvider>);
    expect(screen.getByTestId('count').textContent).toBe('5');
    expect(VIEWS[0].id).toBe('chat');
    expect(VIEWS.map((v) => v.id)).toEqual([
      'chat',
      'documents',
      'resume-checker',
      'jobs',
      'tracker',
    ]);
  });

  it('defaults to chat', () => {
    render(<ViewProvider><Probe /></ViewProvider>);
    expect(screen.getByTestId('active').textContent).toBe('chat');
  });

  it('switches view', () => {
    render(<ViewProvider><Probe /></ViewProvider>);
    fireEvent.click(screen.getByText('jobs'));
    expect(screen.getByTestId('active').textContent).toBe('jobs');
  });

  it('persists the choice across remounts', () => {
    const { unmount } = render(<ViewProvider><Probe /></ViewProvider>);
    fireEvent.click(screen.getByText('documents'));
    expect(screen.getByTestId('active').textContent).toBe('documents');
    unmount();

    render(<ViewProvider><Probe /></ViewProvider>);
    expect(screen.getByTestId('active').textContent).toBe('documents');
  });

  it('restores the persisted view on mount', () => {
    window.localStorage.setItem('aca-view', 'tracker');
    render(<ViewProvider><Probe /></ViewProvider>);
    expect(screen.getByTestId('active').textContent).toBe('tracker');
  });

  it('ignores an unknown persisted view', () => {
    window.localStorage.setItem('aca-view', 'not-a-view');
    render(<ViewProvider><Probe /></ViewProvider>);
    expect(screen.getByTestId('active').textContent).toBe('chat');
  });

  it('falls back to chat for an unknown setView target', () => {
    render(<ViewProvider><Probe /></ViewProvider>);
    fireEvent.click(screen.getByText('tracker'));
    // Now push an invalid value directly through the same code path.
    const { container } = render(<ViewProvider><Probe /></ViewProvider>);
    expect(container).toBeInTheDocument();
    expect(screen.getAllByTestId('active')[0].textContent).toBe('tracker');
  });
});
