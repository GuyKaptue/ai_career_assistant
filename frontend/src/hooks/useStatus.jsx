import React, { createContext, useContext, useMemo, useState } from 'react';

import { debugLog } from '../lib/debug';

const StatusContext = createContext({
  status: 'Ready',
  summary: '',
  report: () => {},
});

/**
 * Shared status channel. Features report transient status messages
 * (already translated via useI18n) and the StatusBanner renders them
 * in an aria-live region so screen readers announce changes.
 */
export function StatusProvider({ children }) {
  const [status, setStatus] = useState('Ready');
  const [summary, setSummary] = useState('');

  const report = useMemo(
    () => (nextStatus, nextSummary = '') => {
      debugLog('status', 'report', { status: nextStatus, summary: String(nextSummary).slice(0, 300) });
      setStatus(nextStatus);
      setSummary(nextSummary);
    },
    [],
  );

  const value = useMemo(() => ({ status, summary, report }), [status, summary, report]);

  return <StatusContext.Provider value={value}>{children}</StatusContext.Provider>;
}

export function useStatus() {
  return useContext(StatusContext);
}
