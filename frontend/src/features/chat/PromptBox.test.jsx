import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../i18n';
import PromptBox from './PromptBox';

/**
 * Composer contract:
 *   - auto-growing multi-line textarea
 *   - live character / estimated-token counter against the prompt budget
 *   - Enter sends, Shift+Enter inserts a newline, IME composition is safe
 *   - the send button becomes a Stop button while a response is generating
 */
/**
 * Renders the composer the way ChatBox does: the parent owns the value, so
 * `onChange` actually updates what PromptBox sees (it is a controlled input).
 */
function renderPromptBox(initial = {}) {
  const handlers = {
    onSend: vi.fn(),
    onStop: vi.fn(),
    onAttachPdf: vi.fn(),
    onRemoveAttachment: vi.fn(),
  };

  function Harness() {
    const [value, setValue] = React.useState(initial.value || '');
    const [attachment, setAttachment] = React.useState(initial.attachment || null);
    return (
      <I18nProvider>
        <PromptBox
          value={value}
          onChange={(next) => { setValue(next); }}
          onSend={handlers.onSend}
          onStop={handlers.onStop}
          onAttachPdf={(file) => { handlers.onAttachPdf(file); setAttachment({ name: file.name }); }}
          onRemoveAttachment={() => { setAttachment(null); handlers.onRemoveAttachment(); }}
          sending={initial.sending || false}
          disabled={initial.disabled || false}
          attachment={attachment}
          placeholder={initial.placeholder || 'Ask anything...'}
        />
      </I18nProvider>
    );
  }

  return { handlers, ...render(<Harness />) };
}

const input = () => screen.getByTestId('prompt-input');
const counter = () => screen.getByTestId('prompt-counter');
const send = () => screen.getByTestId('send-button');

/** Types into the controlled textarea. */
function type(text) {
  fireEvent.change(input(), { target: { value: text } });
}

/** Uploads a file into the (hidden) PDF input. */
function upload(file) {
  fireEvent.change(screen.getByTestId('prompt-file-input'), { target: { files: [file] } });
}

beforeEach(() => {
  document.body.innerHTML = '';
});

describe('PromptBox', () => {
  it('renders a labelled, single-row textarea', () => {
    renderPromptBox();
    expect(input()).toBeInTheDocument();
    expect(input()).toHaveAttribute('rows', '1');
    expect(input()).toHaveAccessibleName('Ask anything...');
  });

  it('grows with the content up to a ceiling, then scrolls', async () => {
    renderPromptBox();
    const el = input();
    // jsdom reports scrollHeight 0, so height is set to the auto-fit value.
    type('one line');
    await waitFor(() => expect(el.style.height).not.toBe(''));
    expect(parseFloat(el.style.height)).toBeLessThanOrEqual(200);
  });

  it('shows a live character and estimated-token counter', () => {
    renderPromptBox();
    expect(counter()).toHaveTextContent('0/8,000 characters');

    type('Hello there');
    expect(counter()).toHaveTextContent('11/8,000 characters');
    expect(counter()).toHaveTextContent('~3 tokens'); // ceil(11 / 4)
  });

  it('warns in the counter as the limit approaches and blocks sending past it', () => {
    renderPromptBox();

    type('x'.repeat(7400)); // 92.5% of 8000
    expect(counter()).not.toHaveClass('text-destructive');
    expect(send()).not.toBeDisabled();

    type('x'.repeat(8100)); // over the limit
    expect(counter()).toHaveClass('text-destructive');
    expect(counter()).toHaveAttribute('role', 'alert');
    expect(send()).toBeDisabled();
  });

  it('Enter sends, Shift+Enter does not', () => {
    const { handlers } = renderPromptBox();
    type('hello');

    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(handlers.onSend).toHaveBeenCalledTimes(1);

    // Shift+Enter must fall through to the textarea (new line).
    fireEvent.keyDown(input(), { key: 'Enter', shiftKey: true });
    expect(handlers.onSend).toHaveBeenCalledTimes(1);
  });

  it('does not send while a response is generating', () => {
    const { handlers } = renderPromptBox({ sending: true });
    type('hello');
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(handlers.onSend).not.toHaveBeenCalled();
  });

  it('Enter never sends while an IME composition is active', () => {
    const { handlers } = renderPromptBox();
    type('你好');

    fireEvent.compositionStart(input());
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(handlers.onSend).not.toHaveBeenCalled();

    fireEvent.compositionEnd(input());
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(handlers.onSend).toHaveBeenCalledTimes(1);
  });

  it('the send button is disabled until there is something to send', () => {
    renderPromptBox();
    expect(send()).toBeDisabled();
    type('  ');
    expect(send()).toBeDisabled();
    type('hi');
    expect(send()).not.toBeDisabled();
  });

  it('replaces the send button with a Stop button while generating', () => {
    const { handlers } = renderPromptBox({ sending: true });
    expect(screen.queryByTestId('send-button')).not.toBeInTheDocument();

    const stop = screen.getByTestId('stop-button');
    expect(stop).toBeInTheDocument();
    expect(stop).toHaveAccessibleName('Stop');

    fireEvent.click(stop);
    expect(handlers.onStop).toHaveBeenCalledTimes(1);
  });

  it('rejects a non-PDF attachment with an alert', () => {
    const { handlers } = renderPromptBox();
    const fileInput = screen.getByTestId('prompt-file-input');

    fireEvent.change(fileInput, {
      target: { files: [new File(['x'], 'notes.txt', { type: 'text/plain' })] },
    });

    expect(screen.getByRole('alert')).toHaveTextContent('Please attach a PDF file.');
    expect(handlers.onAttachPdf).not.toHaveBeenCalled();
  });

  it('rejects an oversized PDF', () => {
    const { handlers } = renderPromptBox();
    const fileInput = screen.getByTestId('prompt-file-input');

    fireEvent.change(fileInput, {
      target: { files: [new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'cv.pdf', { type: 'application/pdf' })] },
    });

    expect(screen.getByRole('alert')).toHaveTextContent('File too large (max 5MB)');
    expect(handlers.onAttachPdf).not.toHaveBeenCalled();
  });

  it('accepts a valid PDF and lets the user remove it again', () => {
    const { handlers } = renderPromptBox();
    const fileInput = screen.getByTestId('prompt-file-input');
    const pdf = new File([new Uint8Array(1024)], 'cv.pdf', { type: 'application/pdf' });

    fireEvent.change(fileInput, { target: { files: [pdf] } });
    expect(handlers.onAttachPdf).toHaveBeenCalledWith(pdf);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    fireEvent.change(fileInput, { target: { files: [pdf] } });
    fireEvent.click(screen.getByLabelText('Remove attachment'));
    expect(handlers.onRemoveAttachment).toHaveBeenCalledTimes(1);
  });

  it('every control is disabled while the whole form is disabled', () => {
    renderPromptBox({ disabled: true });
    expect(input()).toBeDisabled();
    expect(screen.getByLabelText(/Attach CV/)).toBeDisabled();
    expect(screen.queryByTestId('stop-button')).not.toBeInTheDocument();
    expect(send()).toBeDisabled();
  });
});
