import { act, render, renderHook, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../i18n';
import en from '../i18n/locales/en';
import ChatCanvas from '../features/chat/ChatCanvas';
import { useChat } from './useChat';

vi.mock('../lib/api', () => ({
  apiRequestWithSignal: vi.fn(),
}));

import { apiRequestWithSignal } from '../lib/api';

const session = { access_token: 'tok' };

const structuredMatch = {
  intent: 'match_job',
  match: { score: 64, label: 'OK', matched_skills: ['Go'], missing_skills: [], reasons: [] },
  job: { title: 'Dev', company: 'Co' },
};

beforeEach(() => {
  apiRequestWithSignal.mockReset();
  apiRequestWithSignal.mockImplementation((path) => {
    if (path === '/api/v1/chat/sessions') return Promise.resolve({ items: [] });
    if (path.startsWith('/api/v1/chat/sessions/')) return Promise.resolve({ messages: [] });
    return Promise.resolve({});
  });
});

afterEach(() => {
  window.localStorage.removeItem('aca-locale');
});

describe('useChat sendMessage attaches top-level structured', () => {
  it('stores structured + intent from the real response shape (match)', async () => {
    apiRequestWithSignal.mockImplementation((path) => {
      if (path === '/api/v1/chat/sessions') return Promise.resolve({ items: [] });
      if (path.startsWith('/api/v1/chat/sessions/')) return Promise.resolve({ messages: [] });
      return Promise.resolve({
        session: { id: 's1' },
        message: { id: 'a1', role: 'assistant', content: 'Reply text' },
        structured: structuredMatch,
        intent: 'match_job',
      });
    });
    const { result } = renderHook(() => useChat(session));
    await act(async () => { result.current.selectSession('s1'); });
    await act(async () => {
      await result.current.sendMessage('Does my CV match this job?');
    });
    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant.structured).toEqual(structuredMatch);
    expect(assistant.intent).toBe('match_job');

    window.localStorage.setItem('aca-locale', 'en');
    render(<I18nProvider><ChatCanvas messages={[assistant]} onSendText={vi.fn()} /></I18nProvider>);
    expect(screen.getByText(en.chat.matchedSkills)).toBeInTheDocument();
  });

  it('stores structured for a document reply', async () => {
    const structuredDoc = { intent: 'tailor_cv', document: { type: 'cv', content: 'My CV', template_id: 't1' } };
    apiRequestWithSignal.mockImplementation((path) => {
      if (path === '/api/v1/chat/sessions') return Promise.resolve({ items: [] });
      if (path.startsWith('/api/v1/chat/sessions/')) return Promise.resolve({ messages: [] });
      return Promise.resolve({
        session: { id: 's1' },
        message: { id: 'a2', role: 'assistant', content: 'Doc reply' },
        structured: structuredDoc,
        intent: 'tailor_cv',
      });
    });
    const { result } = renderHook(() => useChat(session));
    await act(async () => { result.current.selectSession('s1'); });
    await act(async () => {
      await result.current.sendMessage('Tailor my CV');
    });
    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant.structured).toEqual(structuredDoc);
    expect(assistant.intent).toBe('tailor_cv');
  });

  it('stores structured for a clarify reply', async () => {
    const structuredClarify = { intent: 'clarify', missing: ['job'], job_ingest_status: 'login_wall' };
    apiRequestWithSignal.mockImplementation((path) => {
      if (path === '/api/v1/chat/sessions') return Promise.resolve({ items: [] });
      if (path.startsWith('/api/v1/chat/sessions/')) return Promise.resolve({ messages: [] });
      return Promise.resolve({
        session: { id: 's1' },
        message: { id: 'a3', role: 'assistant', content: 'Need more' },
        structured: structuredClarify,
        intent: 'clarify',
      });
    });
    const { result } = renderHook(() => useChat(session));
    await act(async () => { result.current.selectSession('s1'); });
    await act(async () => {
      await result.current.sendMessage('match');
    });
    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant.structured).toEqual(structuredClarify);
  });

  it('plain general reply with no structured renders no card', async () => {
    apiRequestWithSignal.mockImplementation((path) => {
      if (path === '/api/v1/chat/sessions') return Promise.resolve({ items: [] });
      if (path.startsWith('/api/v1/chat/sessions/')) return Promise.resolve({ messages: [] });
      return Promise.resolve({
        session: { id: 's1' },
        message: { id: 'a4', role: 'assistant', content: 'General reply' },
      });
    });
    const { result } = renderHook(() => useChat(session));
    await act(async () => { result.current.selectSession('s1'); });
    await act(async () => {
      await result.current.sendMessage('hello');
    });
    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant.structured).toBeUndefined();
    expect(assistant.intent).toBeUndefined();
  });

  it('aborted path behaves as before', async () => {
    const abortErr = new Error('aborted');
    abortErr.name = 'AbortError';
    apiRequestWithSignal.mockImplementation((path) => {
      if (path === '/api/v1/chat/sessions') return Promise.resolve({ items: [] });
      if (path.startsWith('/api/v1/chat/sessions/')) return Promise.resolve({ messages: [] });
      return Promise.reject(abortErr);
    });
    const { result } = renderHook(() => useChat(session));
    let ret;
    await act(async () => {
      ret = await result.current.sendMessage('hi');
    });
    expect(ret).toEqual({ aborted: true });
    expect(result.current.error).toBeNull();
  });

  it('error path behaves as before', async () => {
    apiRequestWithSignal.mockImplementation((path) => {
      if (path === '/api/v1/chat/sessions') return Promise.resolve({ items: [] });
      if (path.startsWith('/api/v1/chat/sessions/')) return Promise.resolve({ messages: [] });
      return Promise.reject(new Error('backend down'));
    });
    const { result } = renderHook(() => useChat(session));
    const before = result.current.messages.length;
    let ret;
    await act(async () => {
      ret = await result.current.sendMessage('hi');
    });
    expect(ret).toBeNull();
    expect(result.current.error).toBe('backend down');
    expect(result.current.messages.length).toBe(before);
  });
});
