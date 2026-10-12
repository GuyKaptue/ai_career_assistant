import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

import { debugLog } from '../lib/debug';
import de from './locales/de';
import en from './locales/en';
import fr from './locales/fr';

const locales = { en, de, fr };
const LOCALE_STORAGE_KEY = 'aca-locale';

const I18nContext = createContext({
  locale: 'en',
  availableLocales: ['en'],
  t: (key, varsOrFallback) =>
    typeof varsOrFallback === 'string' ? varsOrFallback : key,
  setLocale: () => {},
});

function translate(dictionary, key) {
  let node = dictionary;
  for (const part of key.split('.')) {
    if (node === undefined || node === null) {
      return key;
    }
    node = node[part];
  }
  return typeof node === 'string' ? node : key;
}

export function I18nProvider({ children }) {
  debugLog('i18n', 'I18nProvider render started (if this line is missing, the module failed before render — see docs/debugging/react-not-defined.md)');
  const [locale, setLocaleState] = useState(() => {
    if (typeof window === 'undefined') {
      return 'en';
    }
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    const resolved = stored && stored in locales ? stored : 'en';
    debugLog('i18n', 'locale resolved', { stored: stored || '(none)', resolved });
    return resolved;
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    } catch {
      // Storage may be unavailable (private mode); ignore.
    }
  }, [locale]);

  const value = useMemo(() => {
    const dictionary = locales[locale] || en;
    /**
     * Translate `key`, optionally interpolating `{name}` placeholders.
     *
     * Supported signatures:
     *   t('key')
     *   t('key', { count: 2 })          — variable interpolation
     *   t('key', 'Fallback text')       — fallback when the key is missing
     *   t('key', 'Fallback', { n: 1 })  — both
     *
     * A missing key returns the fallback when one is given, otherwise
     * the key itself — never an empty string.
     */
    const t = (key, varsOrFallback, maybeVars) => {
      const fallback = typeof varsOrFallback === 'string' ? varsOrFallback : undefined;
      const vars = typeof varsOrFallback === 'object' && varsOrFallback !== null ? varsOrFallback : maybeVars;
      let text = translate(dictionary, key);
      if (text === key && fallback !== undefined) {
        text = fallback;
      }
      if (vars && typeof vars === 'object') {
        for (const [name, replacement] of Object.entries(vars)) {
          text = text.replaceAll(`{${name}}`, String(replacement));
        }
      }
      return text;
    };
    return {
      locale,
      availableLocales: Object.keys(locales),
      t,
      setLocale: setLocaleState,
    };
  }, [locale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
