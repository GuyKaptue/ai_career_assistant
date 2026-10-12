import { useEffect, useState } from 'react';

import { apiRequest } from '../lib/api';

/**
 * Loads the public template catalog once. Falls back to an empty
 * list when the backend is unreachable (the UI keeps working with
 * an empty gallery instead of crashing).
 *
 * @returns {{ templates: import('../types').Template[], loading: boolean, error: Error|null, reload: () => void }}
 */
export function useTemplates() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const payload = await apiRequest('/api/v1/templates');
        if (!isMounted) {
          return;
        }
        setTemplates(Array.isArray(payload.items) ? payload.items : []);
      } catch (fetchError) {
        if (!isMounted) {
          return;
        }
        setError(fetchError);
        setTemplates([]);
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      isMounted = false;
    };
  }, [reloadToken]);

  const reload = () => setReloadToken((token) => token + 1);

  return { templates, loading, error, reload };
}
