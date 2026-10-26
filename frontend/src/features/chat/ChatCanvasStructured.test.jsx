import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../i18n';
import de from '../../i18n/locales/de';
import en from '../../i18n/locales/en';
import * as api from '../../lib/api';
import ChatCanvas from './ChatCanvas';

function renderCanvas(props, locale = 'en') {
  window.localStorage.setItem('aca-locale', locale);
  return render(<I18nProvider><ChatCanvas {...props} /></I18nProvider>);
}
afterEach(() => { window.localStorage.removeItem('aca-locale'); vi.restoreAllMocks(); });

const msg = (structured) => ({ id: 'a1', role: 'assistant', content: 'Reply text', structured });

describe('ChatCanvas structured replies', () => {
  it('match: renders the card and sends localised follow-up prompts', () => {
    const onSendText = vi.fn();
    renderCanvas({
      messages: [msg({ intent: 'match_job', match: { score: 64, label: 'OK', matched_skills: ['Go'], missing_skills: [], reasons: [] }, job: { title: 'Dev', company: 'Co' } })],
      onSendText,
    }, 'de');
    fireEvent.click(screen.getByRole('button', { name: de.chat.tailorCv }));
    expect(onSendText).toHaveBeenLastCalledWith(de.chat.quickTailorPrefill);
    fireEvent.click(screen.getByRole('button', { name: de.chat.writeCover }));
    expect(onSendText).toHaveBeenLastCalledWith(de.chat.quickCoverPrefill);
  });

  it('document: passes the real session to the render call', async () => {
    const spy = vi.spyOn(api, 'apiBlob').mockResolvedValue(new Blob(['x']));
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const session = { access_token: 'real-token' };
    renderCanvas({ messages: [msg({ intent: 'tailor_cv', document: { type: 'cv', content: 'My CV', template_id: 't1' } })], session });
    fireEvent.click(screen.getByRole('button', { name: en.chat.download }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0][1].session).toBe(session);
    expect(spy.mock.calls[0][1].body.content).toBe('My CV');
  });

  it('clarify: submitting a pasted job sends that text as a chat message', () => {
    const onSendText = vi.fn();
    renderCanvas({ messages: [msg({ intent: 'clarify', missing: ['job'], job_ingest_status: 'login_wall' })], onSendText });
    expect(screen.getByText(en.chat.ingest.loginWall)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(en.chat.jobTextPlaceholder), { target: { value: 'Pasted posting' } });
    fireEvent.click(screen.getByRole('button', { name: en.chat.submitJob }));
    expect(onSendText).toHaveBeenCalledTimes(1);
    expect(onSendText).toHaveBeenCalledWith('Pasted posting');
  });

  it('plain replies and unknown intents render no card', () => {
    renderCanvas({ messages: [msg(undefined), { id: 'a2', role: 'assistant', content: 'x', structured: { intent: 'something_new' } }] });
    expect(screen.queryByRole('button', { name: en.chat.download })).toBeNull();
    expect(screen.queryByText(en.chat.matchedSkills)).toBeNull();
  });
});
