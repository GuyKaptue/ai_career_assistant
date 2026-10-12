import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../i18n';
import { ViewProvider } from '../hooks/useView';
import { ThemeProvider } from '../hooks/useTheme';
import { useView } from '../hooks/useView';
import SettingsDialog from './SettingsDialog';

/**
 * Settings dialog: every section (workspaces, appearance, AI models, account)
 * must render and be functional, and navigating to a workspace must close the
 * dialog and change the active view.
 */
const { sessionRef, apiRequestMock } = vi.hoisted(() => ({
  sessionRef: { current: null },
  apiRequestMock: vi.fn(),
}));

vi.mock('../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn(() => Promise.resolve({ data: { session: sessionRef.current } })),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
      signOut: vi.fn(),
      signUp: vi.fn(),
      signInWithPassword: vi.fn(),
    },
  },
}));

vi.mock('../lib/api', () => ({
  apiRequest: apiRequestMock,
  apiRequestWithSignal: apiRequestMock,
  apiUpload: vi.fn(),
  getApiBase: () => '',
}));

/** Reports the active view so navigation can be asserted. */
function ViewProbe() {
  const { view } = useView();
  return <span data-testid="active-view">{view}</span>;
}

function renderSettings(overrides = {}) {
  const onOpenChange = vi.fn();
  const result = render(
    <I18nProvider>
      <ThemeProvider>
        <ViewProvider>
          <ViewProbe />
          <SettingsDialog open={overrides.open ?? true} onOpenChange={onOpenChange} />
        </ViewProvider>
      </ThemeProvider>
    </I18nProvider>,
  );
  return { onOpenChange, ...result };
}

const dialog = () => screen.getByRole('dialog');

beforeEach(() => {
  window.localStorage.clear(); // the language test persists a locale
  sessionRef.current = null;
  apiRequestMock.mockReset().mockResolvedValue({ items: [], count: 0, default: 'auto', auto_default_model: null });
  document.body.innerHTML = '';
});

describe('SettingsDialog', () => {
  it('renders nothing while closed', () => {
    renderSettings({ open: false });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders as a card with header (title + X), content and footer', () => {
    renderSettings();
    const panel = dialog();
    expect(within(panel).getByRole('heading', { level: 2, name: 'Settings' })).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: 'Close' })).toBeInTheDocument();
    expect(within(panel).getByRole('navigation', { name: 'Settings sections' })).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: 'Done' })).toBeInTheDocument();
  });

  it('the X button, the Done button and the overlay all ask to close', () => {
    const { onOpenChange } = renderSettings();
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Close' }));
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Done' }));
    fireEvent.click(dialog().parentElement);
    expect(onOpenChange).toHaveBeenCalledTimes(3);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows the three sections, General first', () => {
    renderSettings();
    const panel = dialog();
    for (const label of ['General', 'AI models', 'Account']) {
      expect(within(panel).getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(within(panel).getByRole('heading', { level: 3, name: 'General' })).toBeInTheDocument();
  });

  it('does not repeat the workspace navigation (it lives in the sidebar)', () => {
    renderSettings();
    expect(within(dialog()).queryByText('Job discovery')).not.toBeInTheDocument();
  });

  it('General shows a working theme radiogroup', async () => {
    renderSettings();

    const radios = within(dialog()).getAllByRole('radio');
    expect(radios).toHaveLength(3);
    expect(within(dialog()).getByRole('radio', { name: 'Light' })).toHaveAttribute('aria-checked', 'false');
    expect(within(dialog()).getByRole('radio', { name: 'System' })).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(within(dialog()).getByRole('radio', { name: 'Dark' }));
    expect(within(dialog()).getByRole('radio', { name: 'Dark' })).toHaveAttribute('aria-checked', 'true');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('General lets the user switch the interface language', () => {
    renderSettings();
    const select = within(dialog()).getByLabelText('Language');
    expect(select.value).toBe('en');
    fireEvent.change(select, { target: { value: 'de' } });
    expect(within(dialog()).getByRole('heading', { level: 3, name: 'Allgemein' })).toBeInTheDocument();
  });

  it('AI Models defaults to Auto and lists the registry models', async () => {
    apiRequestMock.mockResolvedValue({
      count: 2,
      items: [
        { model_id: 'deepseek-ai/DeepSeek-R1', chat_compatible: true },
        { model_id: 'teknium/OpenHermes-2.5-Mistral-7B', chat_compatible: false },
      ],
      default: 'auto',
      auto_default_model: 'deepseek-ai/DeepSeek-R1',
    });

    renderSettings();
    fireEvent.click(within(dialog()).getByRole('button', { name: /AI models/ }));

    const select = within(dialog()).getByLabelText('Model');
    await waitFor(() => expect(select.querySelectorAll('option')).toHaveLength(3));

    // Auto is first and is the selected default.
    expect(select.value).toBe('auto');
    const options = Array.from(select.querySelectorAll('option')).map((o) => o.textContent);
    expect(options[0]).toContain('deepseek-ai/DeepSeek-R1');
    // Unavailable models are labelled rather than hidden.
    expect(options.some((o) => o.includes('unavailable'))).toBe(true);
  });

  it('AI Models lets the user pin a specific model', async () => {
    apiRequestMock.mockResolvedValue({
      count: 1,
      items: [{ model_id: 'microsoft/phi-4', chat_compatible: true }],
      default: 'auto',
      auto_default_model: 'microsoft/phi-4',
    });

    renderSettings();
    fireEvent.click(within(dialog()).getByRole('button', { name: /AI models/ }));
    const select = await within(dialog()).findByLabelText('Model');
    await waitFor(() => expect(select.querySelectorAll('option')).toHaveLength(2));

    fireEvent.change(select, { target: { value: 'microsoft/phi-4' } });
    expect(select.value).toBe('microsoft/phi-4');
  });

  it('Account offers sign-in / sign-up for guests', () => {
    renderSettings();
    fireEvent.click(within(dialog()).getByRole('button', { name: /Account/ }));

    expect(within(dialog()).getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(within(dialog()).getByRole('button', { name: 'Sign up' })).toBeInTheDocument();
  });

  it('Account shows the signed-in user and a sign-out action', async () => {
    sessionRef.current = {
      access_token: 'token',
      user: { email: 'ada@example.com', user_metadata: { name: 'Ada' } },
    };
    renderSettings();
    fireEvent.click(within(dialog()).getByRole('button', { name: /Account/ }));

    // useSession resolves the stored session asynchronously.
    await waitFor(() => expect(within(dialog()).getByText('ada@example.com')).toBeInTheDocument());
    expect(within(dialog()).getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
  });

  it('Escape closes the dialog', async () => {
    const { onOpenChange } = renderSettings();
    fireEvent.keyDown(dialog(), { key: 'Escape' });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
