import { useCallback, useEffect, useRef, useState } from 'react';
import { apiRequestWithSignal } from '../lib/api';

/**
 * Chat session management hook.
 *
 * Wraps the /api/v1/chat endpoints:
 * - lists the user's sessions on mount (auth-gated)
 * - selects, creates, and deletes sessions
 * - sends a message via /api/v1/chat/completions
 *   (the endpoint creates a session when session_id is omitted)
 */
export function useChat(session) {
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Load the session list when the user authenticates.
  useEffect(() => {
    if (!session) {
      setSessions([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    apiRequestWithSignal('/api/v1/chat/sessions', { session })
      .then((data) => {
        if (!cancelled) setSessions(data.items || []);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Failed to load chat sessions');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session?.access_token]);

  // Load messages for the active session.
  useEffect(() => {
    if (!session || !activeSessionId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    apiRequestWithSignal(`/api/v1/chat/sessions/${activeSessionId}`, { session })
      .then((data) => {
        if (!cancelled) setMessages(data.messages || []);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Failed to load session');
      });
    return () => {
      cancelled = true;
    };
  }, [session?.access_token, activeSessionId]);

  const selectSession = useCallback((id) => {
    setActiveSessionId(id);
    setSearchQuery('');
  }, []);

  const newChat = useCallback(() => {
    setActiveSessionId(null);
    setMessages([]);
    setError(null);
    setSearchQuery('');
  }, []);

  const createSession = useCallback(
    async ({ title, mode = 'general' } = {}) => {
      if (!session) return null;
      setError(null);
      try {
        const created = await apiRequestWithSignal('/api/v1/chat/sessions', {
          method: 'POST',
          session,
          body: {
            title: title || new Date().toLocaleString(),
            mode,
          },
        });
        setSessions((prev) => [created, ...prev.filter((s) => s.id !== created.id)]);
        setActiveSessionId(created.id);
        setMessages([]);
        return created;
      } catch (err) {
        setError(err?.message || 'Failed to create chat session');
        return null;
      }
    },
    [session?.access_token]
  );

  const deleteSession = useCallback(
    async (id) => {
      if (!session) return false;
      try {
        await apiRequestWithSignal(`/api/v1/chat/sessions/${id}`, {
          method: 'DELETE',
          session,
        });
        setSessions((prev) => prev.filter((s) => s.id !== id));
        if (activeSessionId === id) {
          setActiveSessionId(null);
          setMessages([]);
        }
        return true;
      } catch (err) {
        setError(err?.message || 'Failed to delete session');
        return false;
      }
    },
    [session?.access_token, activeSessionId]
  );

  const abortRef = useRef(null);

  const sendMessage = useCallback(
    async (message, model_id = null, document_context = '') => {
      if (!session) return null;
      const optimistic = {
        id: `local-${Date.now()}`,
        role: 'user',
        content: message,
      };
      setMessages((prev) => [...prev, optimistic]);
      setSending(true);
      setError(null);

      // A fresh controller per turn so "stop" only cancels the live request.
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const body = { message, model_id, document_context };
        if (activeSessionId) body.session_id = activeSessionId;
        const data = await apiRequestWithSignal('/api/v1/chat/completions', {
          method: 'POST',
          session,
          body,
          signal: controller.signal,
        });
        // A new session may have been created server-side; track it.
        if (data?.session?.id && data.session.id !== activeSessionId) {
          setActiveSessionId(data.session.id);
          setSessions((prev) => {
            if (prev.some((s) => s.id === data.session.id)) return prev;
            return [data.session, ...prev];
          });
        }
        if (data?.message) {
          setMessages((prev) => [...prev, data.message]);
        }
        return data;
      } catch (err) {
        if (err?.name === 'AbortError') {
          // The user stopped generation: keep their prompt, drop the spinner.
          setError(null);
          return { aborted: true };
        }
        setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
        setError(err?.message || 'Failed to send message');
        return null;
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setSending(false);
      }
    },
    [session?.access_token, activeSessionId]
  );

  /** Cancels the in-flight completion, if any. */
  const stopGeneration = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  return {
    sessions,
    activeSessionId,
    messages,
    loading,
    sending,
    error,
    searchQuery,
    setSearchQuery,
    selectSession,
    newChat,
    createSession,
    deleteSession,
    sendMessage,
    stopGeneration,
  };
}