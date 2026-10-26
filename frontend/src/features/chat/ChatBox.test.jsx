import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../i18n';
import ChatBox from './ChatBox';
import { AUTO_MODEL, resetModelSelection } from '../../hooks/useModels';
import { readSelection } from '../../hooks/modelSelection';
import { apiRequest, apiUpload } from '../../lib/api';

/**
 * Composer functionality contract (regression coverage for the broken page):
 *   - the textarea is enabled while the composer is empty, so typing works
 *   - the model picker enables once the model list loads, and the pick is
 *     shared with (and applied to) the outgoing send request
 *   - the attach button is enabled while the composer is empty; a PDF upload
 *     reaches /api/v1/resume/extract and renders the attachment chip
 *   - a guest send that cannot be served opens the sign-in dialog and keeps
 *     the typed draft instead of dropping it silently
 *
 * Design note: these assertions target behaviour only — no styling.
 */

const models = [
  { model_id: 'meta-llama/Llama-3.3-70B-Instruct' },
  { model_id: 'microsoft/phi-4' },
];

vi.mock('../../hooks/useStatus.jsx', () => ({
  useStatus: () => ({ report: vi.fn() }),
}));

vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({ session: null, authLoading: false }),
}));

vi.mock('../../lib/debug', () => ({
  debugLog: vi.fn(),
}));

vi.mock('../../lib/api', () => ({
  apiRequest: vi.fn(),
  apiUpload: vi.fn(),
}));

vi.mock('../../components/ui/dialog', () => ({
  Dialog: ({ open, children }) => (open ? <div data-testid="dialog">{children}</div> : null),
  DialogContent: ({ children }) => <div data-testid="dialog-content">{children}</div>,
  DialogHeader: ({ children }) => <div data-testid="dialog-header">{children}</div>,
  DialogTitle: ({ children }) => <h3 data-testid="dialog-title">{children}</h3>,
  DialogDescription: ({ children }) => <p data-testid="dialog-description">{children}</p>,
  DialogFooter: ({ children }) => <div data-testid="dialog-footer">{children}</div>,
}));

function renderChatBox(props = {}) {
  const onSendMessage =
    props.onSendMessage ?? vi.fn().mockResolvedValue({ message: { id: 'a1', role: 'assistant', content: 'ok' } });
  const utils = render(
    <I18nProvider>
      <ChatBox
        session={{ access_token: 'test-token' }}
        task="career_advice"
        messages={[]}
        sending={false}
        loading={false}
        error={null}
        onSendMessage={onSendMessage}
        onNewChat={vi.fn()}
        onCreateSession={vi.fn()}
        onStopGeneration={vi.fn()}
        {...props}
      />
    </I18nProvider>,
  );
  return { ...utils, onSendMessage };
}

const textarea = () => screen.getByTestId('prompt-input');
const sendButton = () => screen.getByTestId('send-button');
const attachButton = () => screen.getByLabelText(/Attach CV/);
const fileInput = () => screen.getByTestId('prompt-file-input');
const modelPicker = () => screen.getByRole('combobox');

beforeEach(() => {
  document.body.innerHTML = '';
  localStorage.clear();
  resetModelSelection();
  vi.clearAllMocks();
  apiRequest.mockImplementation((path) => {
    if (path.startsWith('/api/v1/models')) {
      return Promise.resolve({
        count: models.length,
        items: models,
        default: 'auto',
        auto_default_model: 'microsoft/phi-4',
      });
    }
    return Promise.resolve({ items: [] });
  });
  apiUpload.mockResolvedValue({ filename: 'cv.pdf', text: 'Extracted CV text', pages: 1, chars: 17 });
});

describe('ChatBox composer functionality', () => {
  it('keeps the textarea enabled while empty so the user can type', async () => {
    renderChatBox();

    expect(textarea()).not.toBeDisabled();
    fireEvent.change(textarea(), { target: { value: 'Hello there' } });
    expect(textarea()).toHaveValue('Hello there');
    await waitFor(() => expect(sendButton()).not.toBeDisabled());
  });

  it('enables the model picker once models load and applies the pick to the send request', async () => {
    const { onSendMessage } = renderChatBox();

    await waitFor(() => expect(modelPicker()).not.toBeDisabled());
    expect(modelPicker()).toHaveValue(AUTO_MODEL);

    fireEvent.change(modelPicker(), { target: { value: 'microsoft/phi-4' } });
    expect(modelPicker()).toHaveValue('microsoft/phi-4');
    // The selection lives in the shared store every consumer reads from.
    expect(readSelection()).toBe('microsoft/phi-4');

    fireEvent.change(textarea(), { target: { value: 'Pin my model' } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(onSendMessage).toHaveBeenCalledWith('Pin my model', 'microsoft/phi-4', expect.any(Object)));
  });

  it('keeps sending "auto" (null) when the picker was never touched', async () => {
    const { onSendMessage } = renderChatBox();

    fireEvent.change(textarea(), { target: { value: 'Auto route me' } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(onSendMessage).toHaveBeenCalledWith('Auto route me', null, expect.any(Object)));
    expect(readSelection()).toBe(AUTO_MODEL);
  });

  it('uploads a PDF to the extractor and shows the attachment chip', async () => {
    const { onSendMessage } = renderChatBox();

    expect(attachButton()).not.toBeDisabled();
    const file = new File([new Uint8Array(1024)], 'cv.pdf', { type: 'application/pdf' });
    fireEvent.change(fileInput(), { target: { files: [file] } });

    await waitFor(() => expect(apiUpload).toHaveBeenCalledTimes(1));
    const [path, options] = apiUpload.mock.calls[0];
    expect(path).toBe('/api/v1/resume/extract');
    expect(options.session).toEqual({ access_token: 'test-token' });
    expect(options.formData).toBeInstanceOf(FormData);
    expect(options.formData.get('file')).toBe(file);

    expect(await screen.findByText('cv.pdf')).toBeInTheDocument();

    // The extracted text is prepended to the next outgoing message.
    fireEvent.change(textarea(), { target: { value: 'Summarise this' } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(onSendMessage).toHaveBeenCalled());
    const [sent] = onSendMessage.mock.calls[0];
    expect(sent).toContain('Extracted CV text');
    expect(sent).toContain('Summarise this');
  });

  it('locks the form only while an upload is in flight', async () => {
    let resolveUpload;
    apiUpload.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveUpload = resolve;
        }),
    );
    renderChatBox();

    const file = new File([new Uint8Array(1024)], 'cv.pdf', { type: 'application/pdf' });
    fireEvent.change(fileInput(), { target: { files: [file] } });
    await waitFor(() => expect(textarea()).toBeDisabled());

    resolveUpload({ filename: 'cv.pdf', text: 'done' });
    await waitFor(() => expect(textarea()).not.toBeDisabled());
  });

  it('opens the sign-in dialog for a guest send that gets no reply, keeping the draft', async () => {
    const onSendMessage = vi.fn().mockResolvedValue(null);
    renderChatBox({ session: null, onSendMessage });

    fireEvent.change(textarea(), { target: { value: 'Hi as a guest' } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(screen.getByTestId('dialog')).toBeInTheDocument());
    expect(onSendMessage).toHaveBeenCalledWith('Hi as a guest', null, expect.any(Object));
    expect(textarea()).toHaveValue('Hi as a guest');
  });
});


