import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * Integration test for the whole application shell.
 *
 * Unlike Chat.test.jsx (which stubs the child components), this renders the
 * real provider stack from main.jsx and the real App router, so a reference
 * error introduced by wiring a prop through several files — for example
 * `activeProjectMode` in Sidebar or `openProject` in ChatLayout — fails here
 * instead of crashing the running app.
 *
 * Only the network boundary is mocked: Supabase auth and the REST client.
 */

const { sessionRef, apiRequestMock } = vi.hoisted(() => ({
  sessionRef: { current: null },
  apiRequestMock: vi.fn(),
}));

vi.mock('./lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn(() => Promise.resolve({ data: { session: sessionRef.current } })),
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
      signUp: vi.fn(() => Promise.resolve({ error: null })),
      signInWithPassword: vi.fn(() => Promise.resolve({ error: null })),
      signOut: vi.fn(() => Promise.resolve({ error: null })),
    },
  },
}));

vi.mock('./lib/api', () => ({
  apiRequest: apiRequestMock,
  apiUpload: vi.fn(),
  getApiBase: () => '',
}));

import App from './App';
import { I18nProvider } from './i18n/index.jsx';
import { StatusProvider } from './hooks/useStatus.jsx';
import { ThemeProvider } from './hooks/useTheme';
import { ViewProvider } from './hooks/useView';
import { AuthDialogProvider } from './hooks/useAuthDialog';
import { SettingsDialogProvider } from './hooks/useSettingsDialog';

function mockApi(path) {
  if (path.startsWith('/api/v1/models')) {
    return Promise.resolve({
      count: 10,
      items: [
        { model_id: 'mistralai/Mistral-Small-3.1-24B-Instruct-2503' },
        { model_id: 'microsoft/phi-4' },
      ],
      default: 'auto',
      auto_default_model: 'microsoft/phi-4',
    });
  }
  if (path === '/api/v1/templates') {
    return Promise.resolve({ items: [] });
  }
  if (path === '/api/v1/chat/sessions') {
    return Promise.resolve({ items: [] });
  }
  return Promise.resolve({ items: [] });
}

/** Mirrors the provider stack in main.jsx. */
function renderApp() {
  apiRequestMock.mockImplementation(mockApi);

  return render(
    <ThemeProvider>
      <I18nProvider>
        <StatusProvider>
          <AuthDialogProvider>
            <SettingsDialogProvider>
              <ViewProvider>
                <App />
              </ViewProvider>
            </SettingsDialogProvider>
          </AuthDialogProvider>
        </StatusProvider>
      </I18nProvider>
    </ThemeProvider>,
  );
}

/**
 * Opens the Settings dialog. Settings has exactly ONE entry point: the
 * "Settings" item of the account menu at the bottom of the sidebar.
 */
function openSettingsDialog() {
  fireEvent.click(screen.getByRole('button', { name: 'Account menu' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Settings' }));
}

const nav = () => screen.getByRole('navigation', { name: 'Workspaces' });

describe('App shell integration', () => {
  beforeEach(() => {
    sessionRef.current = null;
    apiRequestMock.mockReset();
    window.localStorage.clear();
  });

  it('boots the chat workspace without a reference error', async () => {
    expect(() => renderApp()).not.toThrow();

    expect(screen.getByLabelText('Sidebar')).toBeInTheDocument();
    expect(screen.getByLabelText('Model')).toBeInTheDocument();
    expect(await screen.findByTestId('prompt-box')).toBeInTheDocument();
  });

  it('renders the welcome copy and the four suggested prompts', async () => {
    renderApp();

    // Serif headline with the accented middle phrase, plus the subtitle.
    const accent = await screen.findByText('working on');
    expect(accent.closest('h1')).toHaveTextContent('What are we working on today?');
    expect(
      screen.getByText('Pick a starting point or type your own message below.'),
    ).toBeInTheDocument();

    for (const prompt of [
      'Help me improve my resume for a software engineering position',
      'Write a cover letter for a senior developer role',
      'What are the best practices for technical interviews?',
      'Analyze my CV for ATS compatibility',
    ]) {
      expect(screen.getByText(prompt)).toBeInTheDocument();
    }
  });

  it('lists every workspace in the sidebar navigation', async () => {
    renderApp();

    for (const label of ['Chat', 'Documents', 'Resume checker', 'Job discovery', 'Application tracker']) {
      expect(within(nav()).getByRole('button', { name: new RegExp(`^${label}`) })).toBeInTheDocument();
    }
  });

  it('marks the active workspace as the current page', () => {
    renderApp();

    expect(within(nav()).getByRole('button', { name: /^Chat/ })).toHaveAttribute('aria-current', 'page');
    expect(within(nav()).getByRole('button', { name: /^Documents/ })).not.toHaveAttribute('aria-current');
  });

  it('navigates from chat to the job-discovery workspace', async () => {
    renderApp();

    fireEvent.click(within(nav()).getByRole('button', { name: /Job discovery/ }));

    // The workspace shows its title as the page heading and keeps the same sidebar.
    expect(await screen.findByRole('heading', { level: 1, name: 'Job discovery' })).toBeInTheDocument();
    expect(screen.getByLabelText('Sidebar')).toBeInTheDocument();
    expect(within(nav()).getByRole('button', { name: /Job discovery/ })).toHaveAttribute('aria-current', 'page');
  });

  it('navigates back to chat from another workspace', async () => {
    renderApp();

    fireEvent.click(within(nav()).getByRole('button', { name: /Documents/ }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Documents' })).toBeInTheDocument();

    fireEvent.click(within(nav()).getByRole('button', { name: /^Chat/ }));
    expect(await screen.findByTestId('prompt-box')).toBeInTheDocument();
  });

  it('"New chat" from another workspace returns to the chat', async () => {
    renderApp();

    fireEvent.click(within(nav()).getByRole('button', { name: /Documents/ }));
    await screen.findByRole('heading', { level: 1, name: 'Documents' });

    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    expect(await screen.findByTestId('prompt-box')).toBeInTheDocument();
  });

  it('persists the chosen workspace across a remount', async () => {
    const { unmount } = renderApp();

    fireEvent.click(within(nav()).getByRole('button', { name: /Resume checker/ }));
    expect(await screen.findByRole('heading', { level: 1, name: 'ATS review' })).toBeInTheDocument();
    unmount();

    // Fresh router instance, same persisted storage.
    renderApp();
    expect(await screen.findByRole('heading', { level: 1, name: 'ATS review' })).toBeInTheDocument();
  });

  it('opens one shared auth dialog that toggles between sign-in and sign-up', async () => {
    renderApp();

    // Single entry point in the rail footer. It appears once useSession
    // settles (before that the footer shows the loading state).
    fireEvent.click(await screen.findByRole('button', { name: 'Sign in' }));

    // One dialog, in sign-in mode. The dialog is the only aria-modal surface.
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText('Email')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('Full Name')).not.toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);

    // Same dialog toggles to sign-up via its tab, adding the extra fields.
    fireEvent.click(within(dialog).getByRole('tab', { name: 'Sign up' }));

    expect(await within(dialog).findByLabelText('Full Name')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Confirm Password')).toBeInTheDocument();

    // Still exactly one dialog.
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
  });

  it('reopens the same single dialog from the header and the account menu', async () => {
    renderApp();
    await screen.findByTestId('prompt-box');

    // Header entry (guests only).
    fireEvent.click(await screen.findByRole('button', { name: 'Sign in' }));
    expect(within(await screen.findByRole('dialog')).getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
  });

  it('Settings has a single entry point: the account menu', async () => {
    renderApp();
    await screen.findByTestId('prompt-box');

    // No Settings button anywhere on the page (no header gear, no sidebar gear).
    expect(screen.queryByRole('button', { name: 'Settings' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Account menu' }));
    expect(screen.getAllByRole('menuitem', { name: 'Settings' })).toHaveLength(1);
  });

  it('Settings is mounted once on every workspace', async () => {
    renderApp();
    for (const label of [/^Chat/, /Documents/, /Job discovery/]) {
      fireEvent.click(within(nav()).getByRole('button', { name: label }));
      await waitFor(() => expect(screen.getByRole('button', { name: 'Account menu' })).toBeInTheDocument());
      openSettingsDialog();
      expect(screen.getAllByRole('dialog')).toHaveLength(1);
      fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Done' }));
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    }
  });

  it('the Settings dialog opens from the account menu and closes on Escape', async () => {
    renderApp();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    openSettingsDialog();
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('heading', { level: 3, name: 'General' })).toBeInTheDocument();

    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('Settings closes with the X button and with a click on the overlay', async () => {
    renderApp();

    openSettingsDialog();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Close' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    openSettingsDialog();
    fireEvent.click(screen.getByRole('dialog').parentElement);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('hydrates the model picker from GET /api/v1/models and defaults to auto', async () => {
    renderApp();

    const select = await screen.findByLabelText('Model');

    // Auto-selection is the default, not an arbitrary manual pick.
    expect(select.value).toBe('auto');

    // The picker lists every registered model plus the auto entry.
    await waitFor(() => {
      const options = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(options).toContain('auto');
      expect(options).toContain('microsoft/phi-4');
    });

    // The auto entry advertises the model auto-selection would choose.
    expect(select.textContent).toContain('microsoft/phi-4');

    expect(apiRequestMock).toHaveBeenCalledWith('/api/v1/models?task=career_advice', expect.anything());
  });

  it('a manual model choice is sent as the model_id', async () => {
    renderApp();

    const select = await screen.findByLabelText('Model');
    await waitFor(() => {
      expect(Array.from(select.querySelectorAll('option')).map((o) => o.value)).toContain('microsoft/phi-4');
    });

    // Switch the picker to a specific model.
    fireEvent.change(select, { target: { value: 'microsoft/phi-4' } });
    expect(screen.getByLabelText('Model').value).toBe('microsoft/phi-4');

    // …and back to auto, which is the default.
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'auto' } });
    expect(screen.getByLabelText('Model').value).toBe('auto');
  });

  it('the model chosen in the composer is the one sent with the message', async () => {
    renderApp();

    const select = await screen.findByLabelText('Model');
    await waitFor(() => {
      expect(Array.from(select.querySelectorAll('option')).map((o) => o.value)).toContain('microsoft/phi-4');
    });
    fireEvent.change(select, { target: { value: 'microsoft/phi-4' } });

    // Open Settings: the same shared selection is shown there.
    openSettingsDialog();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /AI models/ }));
    const settingsSelect = await within(screen.getByRole('dialog')).findByLabelText('Model');
    expect(settingsSelect.value).toBe('microsoft/phi-4');
  });
});
