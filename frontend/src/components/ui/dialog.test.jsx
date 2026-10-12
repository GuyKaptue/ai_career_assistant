import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Dialog } from './dialog';

/**
 * The dialog base is the shared accessibility contract for the auth and
 * settings dialogs: focus trap, Escape, aria-modal, fade/scale, focus
 * restore. These tests pin that behaviour.
 */
describe('UI/Dialog (components/ui/dialog.jsx)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  function Harness({ onClose }) {
    const [open, setOpen] = React.useState(false);
    return (
      <div>
        <button type="button" onClick={() => setOpen(true)}>
          open
        </button>
        <Dialog
          open={open}
          onOpenChange={(next) => {
            setOpen(next);
            if (!next) onClose?.();
          }}
        >
          <h2>Panel title</h2>
          <button type="button" data-autofocus="true">
            first
          </button>
          <button type="button">middle</button>
          <button type="button">last</button>
        </Dialog>
      </div>
    );
  }

  it('renders nothing while closed', () => {
    render(<Harness />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens with role=dialog and aria-modal', () => {
    render(<Harness />);
    fireEvent.click(screen.getByText('open'));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(within(dialog).getByText('Panel title')).toBeInTheDocument();
  });

  it('moves focus into the panel on open', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText('open'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'first' })).toHaveFocus());
  });

  it('closes on Escape', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText('open'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    // The panel stays mounted for the exit animation, then leaves.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('closes when the overlay is clicked', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText('open'));
    const overlay = screen.getByRole('dialog').parentElement;
    fireEvent.click(overlay);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('traps Tab inside the panel', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText('open'));
    const dialog = screen.getByRole('dialog');
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'first' })).toHaveFocus());

    // Tab from the first element must not leave the panel.
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it('locks background scroll while open', () => {
    render(<Harness />);
    expect(document.body.style.overflow).toBe('');
    fireEvent.click(screen.getByText('open'));
    expect(document.body.style.overflow).toBe('hidden');
  });
});
