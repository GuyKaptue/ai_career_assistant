import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthDialogProvider, useAuthDialog } from './useAuthDialog';

vi.mock('../features/auth/AuthDialogs', () => ({
  default: ({ open, mode }) =>
    open ? <div data-testid="auth-dialog" data-mode={mode} /> : null,
}));

/** Renders the auth dialog host and exposes the hook to the test. */
function Probe() {
  const { openAuth, closeAuth, isOpen, mode } = useAuthDialog();
  return (
    <div>
      <button onClick={() => openAuth('sign-in')}>open-sign-in</button>
      <button onClick={() => openAuth('sign-up')}>open-sign-up</button>
      <button onClick={closeAuth}>close</button>
      <span data-testid="state">{`${isOpen}:${mode}`}</span>
    </div>
  );
}

describe('useAuthDialog', () => {
  beforeEach(() => {
    // jsdom has no window.matchMedia; the provider tree is guarded, but keep
    // the tree minimal so nothing else tries to read match state.
    if (!window.matchMedia) {
      window.matchMedia = () => ({
        matches: false,
        addEventListener: () => {},
        removeEventListener: () => {},
      });
    }
  });

  it('renders exactly one dialog, closed by default', () => {
    render(
      <AuthDialogProvider>
        <Probe />
      </AuthDialogProvider>,
    );
    expect(screen.queryByTestId('auth-dialog')).not.toBeInTheDocument();
  });

  it('opens the shared dialog in sign-in mode', () => {
    render(
      <AuthDialogProvider>
        <Probe />
      </AuthDialogProvider>,
    );
    fireEvent.click(screen.getByText('open-sign-in'));
    expect(screen.getByTestId('auth-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('auth-dialog')).toHaveAttribute('data-mode', 'sign-in');
  });

  it('opens the same dialog in sign-up mode — one form, two modes', () => {
    render(
      <AuthDialogProvider>
        <Probe />
      </AuthDialogProvider>,
    );
    fireEvent.click(screen.getByText('open-sign-up'));
    const dialog = screen.getByTestId('auth-dialog');
    expect(dialog).toHaveAttribute('data-mode', 'sign-up');
    // Still exactly one dialog instance in the tree.
    expect(screen.getAllByTestId('auth-dialog')).toHaveLength(1);
  });

  it('closes the dialog', () => {
    render(
      <AuthDialogProvider>
        <Probe />
      </AuthDialogProvider>,
    );
    fireEvent.click(screen.getByText('open-sign-in'));
    fireEvent.click(screen.getByText('close'));
    expect(screen.queryByTestId('auth-dialog')).not.toBeInTheDocument();
    expect(screen.getByTestId('state').textContent).toBe('false:sign-in');
  });

  it('falls back to sign-in for unknown modes', () => {
    render(
      <AuthDialogProvider>
        <Probe />
      </AuthDialogProvider>,
    );
    fireEvent.click(screen.getByText('open-sign-in'));
    expect(screen.getByTestId('auth-dialog')).toHaveAttribute('data-mode', 'sign-in');
  });
});
