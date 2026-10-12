import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ApplicationTracker from './ApplicationTracker';
import { I18nProvider } from '../../i18n/index.jsx';
import { StatusProvider } from '../../hooks/useStatus.jsx';

vi.mock('../../../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
    },
  },
}));

const session = { user: { email: 'jane@example.com' }, access_token: 'token' };

const applicationsBundle = {
  applications: [
    { id: '1', company: 'Acme', position: 'Data Analyst', status: 'applied' },
    { id: '2', company: 'Globex', position: 'ML Engineer', status: 'interview' },
    { id: '3', company: 'Initech', position: 'Data Scientist', status: 'offer' },
  ],
  loading: false,
  error: null,
  reload: vi.fn(),
  create: vi.fn(),
  move: vi.fn().mockResolvedValue({}),
  remove: vi.fn().mockResolvedValue({}),
};

function renderWithProviders(ui) {
  return render(
    <I18nProvider>
      <StatusProvider>{ui}</StatusProvider>
    </I18nProvider>,
  );
}

describe('ApplicationTracker (Kanban)', () => {
  it('renders one column per pipeline stage', () => {
    renderWithProviders(
      <ApplicationTracker session={session} applicationsBundle={applicationsBundle} />,
    );

    expect(screen.getByText('Applied')).toBeInTheDocument();
    expect(screen.getByText('Interview')).toBeInTheDocument();
    expect(screen.getByText('Offer')).toBeInTheDocument();
    expect(screen.getByText('Rejected')).toBeInTheDocument();
  });

  it('groups applications under their status column', () => {
    renderWithProviders(
      <ApplicationTracker session={session} applicationsBundle={applicationsBundle} />,
    );

    expect(screen.getByText('Data Analyst')).toBeInTheDocument();
    expect(screen.getByText('ML Engineer')).toBeInTheDocument();
    expect(screen.getByText('Data Scientist')).toBeInTheDocument();
  });

  it('moves a card forward when the next-stage button is clicked', async () => {
    renderWithProviders(
      <ApplicationTracker session={session} applicationsBundle={applicationsBundle} />,
    );

    const moveButton = screen.getByRole('button', {
      name: /Move to next stage: Data Analyst/,
    });
    moveButton.click();

    await vi.waitFor(() => {
      expect(applicationsBundle.move).toHaveBeenCalledWith('1', 'interview');
    });
  });

  it('deletes a card when the delete button is clicked', async () => {
    renderWithProviders(
      <ApplicationTracker session={session} applicationsBundle={applicationsBundle} />,
    );

    const deleteButton = screen.getByRole('button', {
      name: /Delete application: Data Analyst/,
    });
    deleteButton.click();

    await vi.waitFor(() => {
      expect(applicationsBundle.remove).toHaveBeenCalledWith('1');
    });
  });

  it('requires a session before the tracker form is interactive', () => {
    renderWithProviders(
      <ApplicationTracker session={null} applicationsBundle={{ ...applicationsBundle, applications: [] }} />,
    );

    expect(screen.getByText('Sign in required')).toBeInTheDocument();
  });
});
