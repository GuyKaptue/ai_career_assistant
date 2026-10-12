import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AuthDialogs from './AuthDialogs';
import { I18nProvider } from '../../i18n';

// Supabase is the network boundary: stub it so the tests assert what is sent
// rather than talking to the real project.
const { signInWithPassword, signUp, signOut } = vi.hoisted(() => ({
  signInWithPassword: vi.fn(),
  signUp: vi.fn(),
  signOut: vi.fn(),
}));
vi.mock('../../lib/supabase', () => ({
  supabase: {
    auth: {
      signInWithPassword,
      signUp,
      signOut,
      getSession: vi.fn(() => Promise.resolve({ data: { session: null } })),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    },
  },
}));

beforeEach(() => {
  signInWithPassword.mockReset().mockResolvedValue({ error: null });
  signUp.mockReset().mockResolvedValue({ error: null });
  document.body.innerHTML = '';
});

/**
 * The auth dialog is a single dialog with two tabs (sign in | sign up).
 * These tests pin the ARIA tabs contract, the inline validation, the
 * loading/disabled state, and that the submit payload matches what
 * `supabase.auth` expects.
 */
/**
 * Renders the dialog the way a real parent does: the parent owns `open`, so
 * `onOpenChange(false)` actually closes it (and the controlled-dialog contract
 * is exercised rather than mocked away).
 */
function renderAuth(overrides = {}) {
  const onSuccess = vi.fn();
  const onModeChange = vi.fn();
  const initialMode = overrides.mode || 'sign-in';

  function Harness() {
    const [open, setOpen] = React.useState(overrides.open ?? true);
    const [mode, setMode] = React.useState(initialMode);
    return (
      <I18nProvider>
        <AuthDialogs
          open={open}
          mode={mode}
          onOpenChange={setOpen}
          onSuccess={onSuccess}
          onModeChange={(next) => {
            setMode(next);
            onModeChange(next);
          }}
        />
      </I18nProvider>
    );
  }

  return {
    onSuccess,
    onModeChange,
    open: () => screen.queryByRole('dialog') !== null,
    ...render(<Harness />),
  };
}

const dialog = () => screen.getByRole('dialog');

describe('AuthDialogs', () => {
  it('renders nothing while closed', () => {
    renderAuth({ open: false });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders one dialog with two tabs, sign in selected by default', () => {
    renderAuth();
    const tabs = within(dialog()).getAllByRole('tab');
    expect(tabs).toHaveLength(2);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[1]).toHaveAttribute('aria-selected', 'false');
    expect(within(dialog()).getByLabelText('Email')).toBeInTheDocument();
    // Sign-up-only fields are hidden in the sign-in tab.
    expect(within(dialog()).queryByLabelText('Full Name')).not.toBeInTheDocument();
  });

  it('each tab controls its own panel', () => {
    renderAuth();
    const signInTab = within(dialog()).getByRole('tab', { name: 'Sign in' });
    expect(signInTab).toHaveAttribute('aria-controls', 'auth-panel-sign-in');
    const panel = within(dialog()).getByRole('tabpanel');
    expect(panel.id).toBe('auth-panel-sign-in');
  });

  it('switching to the sign-up tab reveals name and confirm password', () => {
    renderAuth();
    fireEvent.click(within(dialog()).getByRole('tab', { name: 'Sign up' }));

    expect(within(dialog()).getByRole('tab', { name: 'Sign up' })).toHaveAttribute('aria-selected', 'true');
    expect(within(dialog()).getByLabelText('Full Name')).toBeInTheDocument();
    expect(within(dialog()).getByLabelText('Confirm Password')).toBeInTheDocument();
  });

  it('arrow keys move between tabs', () => {
    renderAuth();
    within(dialog()).getByRole('tab', { name: 'Sign in' }).focus();
    fireEvent.keyDown(within(dialog()).getByRole('tablist'), { key: 'ArrowRight' });
    expect(within(dialog()).getByRole('tab', { name: 'Sign up' })).toHaveAttribute('aria-selected', 'true');
  });

  it('blocked submit reveals inline validation tied to the fields', async () => {
    const supabase = { supabase: { auth: { signInWithPassword, signUp } } };
    renderAuth();
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Sign in' }));

    const emailError = await within(dialog()).findByText('Enter your email address.');
    expect(emailError).toHaveAttribute('role', 'alert');
    const email = within(dialog()).getByLabelText('Email');
    expect(email).toHaveAttribute('aria-invalid', 'true');
    expect(email).toHaveAttribute('aria-describedby', 'auth-email-error');
    expect(supabase.supabase.auth.signInWithPassword).not.toHaveBeenCalled();
  });

  it('rejects a malformed email', async () => {
    renderAuth();
    fireEvent.change(within(dialog()).getByLabelText('Email'), { target: { value: 'not-an-email' } });
    fireEvent.change(within(dialog()).getByLabelText('Password'), { target: { value: 'secret123' } });
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Sign in' }));
    expect(await within(dialog()).findByText('Enter a valid email address.')).toBeInTheDocument();
  });

  it('sign-up reports mismatched passwords and a too-short password', async () => {
    renderAuth();
    fireEvent.click(within(dialog()).getByRole('tab', { name: 'Sign up' }));
    fireEvent.change(within(dialog()).getByLabelText('Full Name'), { target: { value: 'Ada' } });
    fireEvent.change(within(dialog()).getByLabelText('Email'), { target: { value: 'ada@example.com' } });
    fireEvent.change(within(dialog()).getByLabelText('Password'), { target: { value: 'short' } });
    fireEvent.change(within(dialog()).getByLabelText('Confirm Password'), { target: { value: 'other' } });
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Create account' }));

    expect(await within(dialog()).findByText('Passwords do not match.')).toBeInTheDocument();
    expect(within(dialog()).getByText('Password must be at least 6 characters.')).toBeInTheDocument();
  });

  it('calls supabase sign-in with the typed credentials', async () => {
    const supabase = { supabase: { auth: { signInWithPassword, signUp } } };
    renderAuth();
    fireEvent.change(within(dialog()).getByLabelText('Email'), { target: { value: 'ada@example.com' } });
    fireEvent.change(within(dialog()).getByLabelText('Password'), { target: { value: 'secret123' } });
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Sign in' }));

    await waitFor(() =>
      expect(supabase.supabase.auth.signInWithPassword).toHaveBeenCalledWith({
        email: 'ada@example.com',
        password: 'secret123',
      }),
    );
    expect(supabase.supabase.auth.signUp).not.toHaveBeenCalled();
  });

  it('disables the fields and shows a loading state while pending', async () => {
    const supabase = { supabase: { auth: { signInWithPassword, signUp } } };
    let release;
    supabase.supabase.auth.signInWithPassword.mockImplementation(
      () => new Promise((resolve) => { release = () => resolve({ error: null }); }),
    );

    renderAuth();
    if (!screen.queryByRole('dialog')) throw new Error('BEFORE CLICK: dialog closed, body=' + document.body.innerHTML.slice(0, 400));
    fireEvent.change(within(dialog()).getByLabelText('Email'), { target: { value: 'ada@example.com' } });
    fireEvent.change(within(dialog()).getByLabelText('Password'), { target: { value: 'secret123' } });
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Sign in' }));

    // While pending: fields and submit are disabled, submit shows the spinner.
    await waitFor(() => expect(within(dialog()).getByLabelText('Email')).toBeDisabled());
    expect(within(dialog()).getByLabelText('Password')).toBeDisabled();
    const submit = within(dialog()).getByRole('button', { name: 'Loading…' });
    expect(submit).toBeDisabled();

    expect(release).toBeTypeOf('function');
    release();

    // On success the dialog closes, so the form leaves the DOM. (The panel
    // stays mounted for its exit animation first, hence waitFor.)
    await waitFor(() => expect(screen.queryByLabelText('Email')).toBeNull());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('surfaces an auth failure as an alert instead of throwing', async () => {
    const supabase = { supabase: { auth: { signInWithPassword, signUp } } };
    supabase.supabase.auth.signInWithPassword.mockResolvedValue({ error: { message: 'Invalid login credentials' } });

    renderAuth();
    fireEvent.change(within(dialog()).getByLabelText('Email'), { target: { value: 'ada@example.com' } });
    fireEvent.change(within(dialog()).getByLabelText('Password'), { target: { value: 'secret123' } });
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Sign in' }));

    const alert = await within(dialog()).findByRole('alert');
    expect(alert).toHaveTextContent('Invalid login credentials');
    // The dialog stays open so the user can retry.
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('clears every field when it closes, leaving no credentials behind', () => {
    const { props, unmount } = renderAuth();
    fireEvent.change(within(dialog()).getByLabelText('Email'), { target: { value: 'ada@example.com' } });
    fireEvent.change(within(dialog()).getByLabelText('Password'), { target: { value: 'secret123' } });
    unmount();

    renderAuth(props);
    expect(within(dialog()).getByLabelText('Email').value).toBe('');
    expect(within(dialog()).getByLabelText('Password').value).toBe('');
  });
});
