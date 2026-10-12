import { describe, expect, it, vi } from 'vitest';

import { debugLog, getDebugBuffer } from './debug';

describe('debugLog', () => {
  it('prints a namespaced console.debug line', () => {
    const spy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    debugLog('boot', 'hello world');
    expect(spy).toHaveBeenCalledWith('[ACA:boot] hello world');
    spy.mockRestore();
  });

  it('appends timestamped entries to the buffer', () => {
    const before = getDebugBuffer().length;
    debugLog('i18n', 'locale resolved', { resolved: 'de' });
    const entries = getDebugBuffer();
    expect(entries.length).toBe(before + 1);
    const last = entries[entries.length - 1];
    expect(last.scope).toBe('i18n');
    expect(last.message).toBe('locale resolved');
    expect(last.data).toEqual({ resolved: 'de' });
    expect(typeof last.at).toBe('string');
  });
});
