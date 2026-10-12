import { useCallback, useEffect, useState } from 'react';

import { apiRequest } from '../lib/api';

/**
 * Application tracker data access. Loads the signed-in user's
 * applications and exposes create/move/remove mutations that keep
 * local state in sync with the backend (FE-04 Kanban operations).
 *
 * @param {Object|null} session Supabase session; null clears the list.
 */
export function useApplications(session) {
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    if (!session) {
      setApplications([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const payload = await apiRequest('/api/v1/applications', { session });
      setApplications(Array.isArray(payload.items) ? payload.items : []);
    } catch (fetchError) {
      setError(fetchError);
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    reload();
  }, [reload]);

  const create = useCallback(
    async (data) => {
      const created = await apiRequest('/api/v1/applications', {
        method: 'POST',
        session,
        body: data,
      });
      setApplications((current) => [created, ...current]);
      return created;
    },
    [session],
  );

  const move = useCallback(
    async (id, status) => {
      const updated = await apiRequest(`/api/v1/applications/${id}/status`, {
        method: 'PATCH',
        session,
        body: { status },
      });
      setApplications((current) =>
        current.map((application) => (application.id === id ? updated : application)),
      );
      return updated;
    },
    [session],
  );

  const remove = useCallback(
    async (id) => {
      await apiRequest(`/api/v1/applications/${id}`, { method: 'DELETE', session });
      setApplications((current) => current.filter((application) => application.id !== id));
    },
    [session],
  );

  return { applications, loading, error, reload, create, move, remove };
}
