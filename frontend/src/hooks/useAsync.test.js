import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useAsync } from './useAsync';

describe('useAsync', () => {
  it('starts idle with no data', () => {
    const { result } = renderHook(() => useAsync());

    expect(result.current.phase).toBe('idle');
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('transitions loading → success and returns the data', async () => {
    let resolveTask;
    const operation = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveTask = resolve;
        }),
    );
    const { result } = renderHook(() => useAsync());

    await act(async () => {
      result.current.run(operation);
    });
    expect(result.current.phase).toBe('loading');

    await act(async () => {
      resolveTask({ value: 42 });
    });

    expect(result.current.phase).toBe('success');
    expect(result.current.data).toEqual({ value: 42 });
    expect(result.current.error).toBeNull();
  });

  it('transitions loading → error and keeps the error', async () => {
    let rejectTask;
    const operation = vi.fn().mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectTask = reject;
        }),
    );
    const { result } = renderHook(() => useAsync());

    await act(async () => {
      result.current.run(operation);
    });
    expect(result.current.phase).toBe('loading');

    await act(async () => {
      rejectTask(new Error('backend down'));
    });

    expect(result.current.phase).toBe('error');
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error.message).toBe('backend down');
  });

  it('retry re-runs the last operation', async () => {
    let calls = 0;
    let resolveTask;
    const operation = vi.fn().mockImplementation(
      () =>
        new Promise((resolve, reject) => {
          calls += 1;
          resolveTask = calls < 2 ? reject : resolve;
        }),
    );
    const { result } = renderHook(() => useAsync());

    await act(async () => {
      result.current.run(operation);
    });
    await act(async () => {
      resolveTask(new Error('flaky'));
    });
    expect(result.current.phase).toBe('error');

    await act(async () => {
      result.current.retry();
    });
    await act(async () => {
      resolveTask('ok');
    });

    expect(result.current.phase).toBe('success');
    expect(result.current.data).toBe('ok');
    expect(operation).toHaveBeenCalledTimes(2);
  });
});
