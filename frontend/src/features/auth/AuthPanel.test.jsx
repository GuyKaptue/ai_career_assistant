import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import AuthPanel from './AuthPanel';
import { I18nProvider } from '../../i18n/index.jsx';
import { StatusProvider } from '../../hooks/useStatus.jsx';

vi.mock('../../../lib/supabase', () => ({
  supabase: {
    auth: {
      signUp: vi.fn().mockResolvedValue({ error: null }),
      signInWithPassword: vi.fn().mockResolvedValue({ error: null }),
      signOut: vi.fn().mockResolvedValue({}),
    },
  },
}));

function renderWithProviders(ui) {
  return render(
    <I18nProvider>
      <StatusProvider>{ui}</StatusProvider>
    </I18nProvider>,
  );
}

describe('AuthPanel', () => {
  it('renders the sign-in form when signed out', () => {
    renderWithProviders(<AuthPanel session={null} authLoading={false} />);

    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByLabelText('Auth mode')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Sign in' }),
    ).toBeInTheDocument();
  });

  it('shows the signed-in user email and a sign-out button', () => {
    const session = { user: { email: 'jane@example.com' }, access_token: 'token' };
    renderWithProviders(<AuthPanel session={session} authLoading={false} />);

    expect(screen.getByText('Signed in')).toBeInTheDocument();
    expect(screen.getByText('jane@example.com')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
  });

  it('disables the submit button while the session is loading', () => {
    renderWithProviders(<AuthPanel session={null} authLoading />);

    expect(screen.getByRole('button', { name: 'Loading…' })).toBeDisabled();
  });
});
