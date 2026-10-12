import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { apiRequest } from '../lib/api';
export { AUTO_MODEL, resetModelSelection } from './modelSelection';
import { AUTO_MODEL, readSelection, subscribeToSelection, writeSelection } from './modelSelection';

/**
 * Fetch the routable model list for the chat model picker.
 *
 * GET /api/v1/models is public (no user data), so it works for guests too.
 * Returns only picker-relevant metadata — never tokens or internals.
 *
 * The picker always shows an "Auto" entry first and defaults to it, so a new
 * user gets automatic model selection rather than an arbitrary manual pick.
 */
export function useModels(session, task = null) {
  const [models, setModels] = useState([]);
  const [autoDefaultModel, setAutoDefaultModel] = useState(null);
  const selectedModel = useSyncExternalStore(subscribeToSelection, readSelection, readSelection);
  const setSelectedModel = writeSelection;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const taskRef = useRef(task);
  taskRef.current = task;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const query = taskRef.current ? `?task=${encodeURIComponent(taskRef.current)}` : '';
    apiRequest(`/api/v1/models${query}`, { session })
      .then((data) => {
        if (cancelled) return;
        setModels(Array.isArray(data.items) ? data.items : []);
        setAutoDefaultModel(data.auto_default_model || null);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Failed to load models');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session?.access_token, task]);

  // A pinned model that left the registry must not keep being sent.
  useEffect(() => {
    if (
      models.length > 0 &&
      selectedModel !== AUTO_MODEL &&
      !models.some((model) => model.model_id === selectedModel)
    ) {
      writeSelection(AUTO_MODEL);
    }
  }, [models, selectedModel]);

  /** True when the user has left model selection to the router. */
  const isAuto = selectedModel === AUTO_MODEL;

  return { models, selectedModel, setSelectedModel, autoDefaultModel, isAuto, loading, error };
}
