import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AuthDialogs from './AuthDialogs';
import { I18nProvider } from '../../i18n';

// Supabase is the network boundary: stub it so the tests assert what is sent
// rather than talking to the real project. lib/api is stubbed too — it is the
// backend boundary AuthDialogs now uses to verify the profiles row.
const { signInWithPassword, signUp, signOut, apiRequest } = vi.hoisted(() => ({
  signInWithPassword: vi.fn(),
  signUp: vi.fn(),
  signOut: vi.fn(),
  apiRequest: vi.fn(),
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
vi.mock('../../lib/api', () => ({
  apiRequest: apiRequest,
}));

// Shape returned by supabase-js v2 on success.
const FAKE_SESSION = { access_token: 'test-token', user: { id: 'user-1', email: 'ada@example.com' } };

beforeEach(() => {
  signInWithPassword.mockReset().mockResolvedValue({ error: null, data: { session: FAKE_SESSION, user: FAKE_SESSION.user } });
  signUp.mockReset().mockResolvedValue({ error: null, data: { session: FAKE_SESSION, user: FAKE_SESSION.user } });
  signOut.mockReset().mockResolvedValue({ error: null });
  // Default: the profiles row already exists (DB trigger created it).
  apiRequest.mockReset().mockResolvedValue({ user_id: 'user-1', email: 'ada@example.com' });
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

  it('calls supabase sign-in with the typed credentials and verifies the profile row', async () => {
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
    // The profile row is verified with the session token before success.
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith('/api/v1/profiles/user-1', { session: FAKE_SESSION }));
    expect(signOut).not.toHaveBeenCalled();
  });

  it('disables the fields and shows a loading state while pending', async () => {
    const supabase = { supabase: { auth: { signInWithPassword, signUp } } };
    let release;
    supabase.supabase.auth.signInWithPassword.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ error: null, data: { session: FAKE_SESSION, user: FAKE_SESSION.user } });
        }),
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

  /**
   * Regression: "signed up but no user record". Supabase created the auth
   * user but nothing created the public.profiles row, and the dialog still
   * reported success. Sign-in/sign-up must verify the row exists (creating
   * it when missing) before the user is shown as signed in.
   */
  it('sign-up creates the profile row when it is missing, then reports success', async () => {
    // GET 404 (missing) -> POST create -> GET verify.
    apiRequest
      .mockRejectedValueOnce(new Error('Profile not found.'))
      .mockResolvedValueOnce({ user_id: 'user-1', email: 'ada@example.com' })
      .mockResolvedValueOnce({ user_id: 'user-1', email: 'ada@example.com' });

    const { onSuccess } = renderAuth();
    fireEvent.click(within(dialog()).getByRole('tab', { name: 'Sign up' }));
    fireEvent.change(within(dialog()).getByLabelText('Full Name'), { target: { value: 'Ada' } });
    fireEvent.change(within(dialog()).getByLabelText('Email'), { target: { value: 'ada@example.com' } });
    fireEvent.change(within(dialog()).getByLabelText('Password'), { target: { value: 'secret123' } });
    fireEvent.change(within(dialog()).getByLabelText('Confirm Password'), { target: { value: 'secret123' } });
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Create account' }));

    await waitFor(() => expect(signUp).toHaveBeenCalledWith({
      email: 'ada@example.com',
      password: 'secret123',
      options: { data: { name: 'Ada' } },
    }));
    // 1. check, 2. create with the typed name, 3. verify persistence.
    await waitFor(() => expect(apiRequest).toHaveBeenCalledTimes(3));
    expect(apiRequest).toHaveBeenNthCalledWith(1, '/api/v1/profiles/user-1', { session: FAKE_SESSION });
    expect(apiRequest).toHaveBeenNthCalledWith(2, '/api/v1/profiles', {
      method: 'POST',
      session: FAKE_SESSION,
      body: { full_name: 'Ada' },
    });
    expect(apiRequest).toHaveBeenNthCalledWith(3, '/api/v1/profiles/user-1', { session: FAKE_SESSION });
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith('sign-up'));
    expect(signOut).not.toHaveBeenCalled();
    // The panel stays mounted for its exit animation first, hence waitFor.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('sign-up does not report success when the profile row cannot be verified', async () => {
    // Every backend call fails: row missing and creation impossible.
    apiRequest.mockRejectedValue(new Error('The database could not be reached.'));

    const { onSuccess } = renderAuth();
    fireEvent.click(within(dialog()).getByRole('tab', { name: 'Sign up' }));
    fireEvent.change(within(dialog()).getByLabelText('Full Name'), { target: { value: 'Ada' } });
    fireEvent.change(within(dialog()).getByLabelText('Email'), { target: { value: 'ada@example.com' } });
    fireEvent.change(within(dialog()).getByLabelText('Password'), { target: { value: 'secret123' } });
    fireEvent.change(within(dialog()).getByLabelText('Confirm Password'), { target: { value: 'secret123' } });
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Create account' }));

    const alert = await within(dialog()).findByRole('alert');
    expect(alert).toHaveTextContent('The database could not be reached.');
    // The half-created session is rolled back and the dialog stays open.
    expect(signOut).toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('sign-in self-heals a legacy user with no profile row', async () => {
    // Users registered before the trigger existed have no profiles row:
    // check misses, create runs without a name (sign-in has none), verify passes.
    apiRequest
      .mockRejectedValueOnce(new Error('Profile not found.'))
      .mockResolvedValueOnce({ user_id: 'user-1', email: 'ada@example.com' })
      .mockResolvedValueOnce({ user_id: 'user-1', email: 'ada@example.com' });

    const { onSuccess } = renderAuth();
    fireEvent.change(within(dialog()).getByLabelText('Email'), { target: { value: 'ada@example.com' } });
    fireEvent.change(within(dialog()).getByLabelText('Password'), { target: { value: 'secret123' } });
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Sign in' }));

    await waitFor(() => expect(apiRequest).toHaveBeenNthCalledWith(2, '/api/v1/profiles', {
      method: 'POST',
      session: FAKE_SESSION,
      body: { full_name: '' },
    }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith('sign-in'));
    expect(signOut).not.toHaveBeenCalled();
  });

  it('sign-up without a session defers profile verification to email confirmation', async () => {
    // Confirmation flow: supabase returns no session, so there is no token
    // to call the backend with — the message tells the user to confirm.
    signUp.mockResolvedValue({ error: null, data: { session: null, user: { id: 'user-2' } } });

    const { onSuccess } = renderAuth();
    fireEvent.click(within(dialog()).getByRole('tab', { name: 'Sign up' }));
    fireEvent.change(within(dialog()).getByLabelText('Full Name'), { target: { value: 'Ada' } });
    fireEvent.change(within(dialog()).getByLabelText('Email'), { target: { value: 'ada@example.com' } });
    fireEvent.change(within(dialog()).getByLabelText('Password'), { target: { value: 'secret123' } });
    fireEvent.change(within(dialog()).getByLabelText('Confirm Password'), { target: { value: 'secret123' } });
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Create account' }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith('sign-up'));
    // No token means no backend round-trip and no rollback.
    expect(apiRequest).not.toHaveBeenCalled();
    expect(signOut).not.toHaveBeenCalled();
  });
});

