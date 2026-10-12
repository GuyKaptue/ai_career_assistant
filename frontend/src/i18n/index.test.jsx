import React from 'react';
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { I18nProvider, useI18n } from '../i18n/index.jsx';

vi.mock('../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
    },
  },
}));

describe('I18nProvider', () => {
  it('defaults to English and translates keys', () => {
    const { result } = renderHook(() => useI18n(), {
      wrapper: I18nProvider,
    });

    expect(result.current.locale).toBe('en');
    expect(result.current.t('app.title')).toBe('AI Career Assistant');
  });

  it('interpolates variables into translated strings', () => {
    const { result } = renderHook(() => useI18n(), {
      wrapper: I18nProvider,
    });

    expect(result.current.t('summary.jobsFound', { count: 7 })).toBe(
      'Found 7 matching opportunities.',
    );
  });

  it('falls back to the key for missing translations', () => {
    const { result } = renderHook(() => useI18n(), {
      wrapper: I18nProvider,
    });

    expect(result.current.t('does.not.exist')).toBe('does.not.exist');
  });

  it('switches locale and translates the new language', () => {
    const { result } = renderHook(() => useI18n(), {
      wrapper: I18nProvider,
    });

    act(() => {
      result.current.setLocale('de');
    });

    expect(result.current.locale).toBe('de');
    expect(result.current.t('app.title')).toBe('KI-Karriereassistent');
  });

  it('exposes the available locales', () => {
    const { result } = renderHook(() => useI18n(), {
      wrapper: I18nProvider,
    });

    expect(result.current.availableLocales).toEqual(['en', 'de', 'fr']);
  });
});
