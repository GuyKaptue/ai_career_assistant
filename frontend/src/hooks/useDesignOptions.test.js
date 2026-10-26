import { renderHook, act, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../lib/api', () => ({ apiRequest: vi.fn() }));

import { apiRequest } from '../lib/api';
import { toApiCountry, useDesignOptions } from './useDesignOptions';

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe('toApiCountry', () => {
  it('maps the "other" choice to the world default code XX', () => {
    expect(toApiCountry('other')).toBe('XX');
  });

  it('passes ISO codes through and normalises empty values', () => {
    expect(toApiCountry('DE')).toBe('DE');
    expect(toApiCountry('BE')).toBe('BE');
    expect(toApiCountry('')).toBe('');
    expect(toApiCountry(undefined)).toBe('');
    expect(toApiCountry(null)).toBe('');
  });
});

describe('useDesignOptions.fetchCountryProfile', () => {
  it('always sends a language and maps other -> XX (BE sends its language)', async () => {
    apiRequest.mockResolvedValue({ cv_layout: 'two_column', paper_size: 'A4' });
    const { result } = renderHook(() => useDesignOptions('cv'));

    await act(async () => {
      await result.current.fetchCountryProfile('BE', 'fr');
    });
    const countryUrls = apiRequest.mock.calls
      .map(([path]) => path)
      .filter((path) => path.includes('country-profiles'));
    expect(countryUrls).toHaveLength(1);
    expect(countryUrls[0]).toContain('country=BE');
    expect(countryUrls[0]).toContain('language=fr');

    // No language supplied -> defaults to "en", never the string "undefined".
    await act(async () => {
      await result.current.fetchCountryProfile('other');
    });
    const urls = apiRequest.mock.calls
      .map(([path]) => path)
      .filter((path) => path.includes('country-profiles'));
    expect(urls[1]).toContain('country=XX');
    expect(urls[1]).toContain('language=en');
    expect(urls[1]).not.toContain('undefined');
  });

  it('ignores a stale (superseded) response so only the newest country wins', async () => {
    let resolveSlow;
    const slow = new Promise((resolve) => {
      resolveSlow = resolve;
    });

    apiRequest.mockImplementation((path) => {
      if (path.includes('/api/v1/themes')) return Promise.resolve({ items: [] });
      if (path.includes('country=DE')) return slow; // slow, will be superseded
      if (path.includes('country=US')) {
        return Promise.resolve({ cv_layout: 'single_column', paper_size: 'Letter' });
      }
      return Promise.resolve({});
    });

    const { result } = renderHook(() => useDesignOptions('cv'));

    // Kick off a slow DE request, then a fast US request that supersedes it.
    let slowPromise;
    act(() => {
      slowPromise = result.current.fetchCountryProfile('DE', 'de');
    });
    await act(async () => {
      await result.current.fetchCountryProfile('US', 'en');
    });
    await waitFor(() => {
      expect(result.current.countryProfile).toEqual({
        cv_layout: 'single_column',
        paper_size: 'Letter',
      });
    });

    // Resolve the stale DE response late; it must NOT overwrite the US profile.
    await act(async () => {
      resolveSlow({ cv_layout: 'two_column', paper_size: 'A4' });
      await slowPromise;
    });
    expect(result.current.countryProfile).toEqual({
      cv_layout: 'single_column',
      paper_size: 'Letter',
    });
  });
});
