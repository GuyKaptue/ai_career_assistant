import { useCallback, useRef, useState } from 'react';

/**
 * Minimal async state machine for data fetching.
 *
 * Returns { phase, data, error, run, retry } where `run` accepts an
 * async operation, tracks loading/error/success, and `retry` re-runs
 * the most recent operation (FE-03 retry requirement).
 *
 * @template T
 * @param {() => Promise<T>} initialOperation
 */
export function useAsync(initialOperation) {
  const [state, setState] = useState({ phase: 'idle', data: null, error: null });
  const lastOperation = useRef(initialOperation ?? null);

  const run = useCallback(async (operation) => {
    const task = operation ?? lastOperation.current;
    if (!task) {
      return null;
    }
    lastOperation.current = task;
    setState({ phase: 'loading', data: null, error: null });
    try {
      const data = await task();
      setState({ phase: 'success', data, error: null });
      return data;
    } catch (error) {
      setState({ phase: 'error', data: null, error });
      return null;
    }
  }, []);

  const retry = useCallback(() => run(), [run]);

  return { ...state, run, retry };
}
