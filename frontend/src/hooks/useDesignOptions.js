import { useState, useEffect, useCallback, useRef } from 'react';

import { apiRequest } from '../lib/api';

const DEFAULT_DESIGN = { themeId: '', country: '', sidebar: '' };

/**
 * Map a country choice to the ISO code the backend expects.
 * The studio offers "Other" (value ``other``) for countries outside the
 * list; the backend/API uses the world default code ``XX`` for it.
 */
export function toApiCountry(country) {
  if (!country) return '';
  return country === 'other' ? 'XX' : country;
}

/**
 * Persists client-side design options per document type in localStorage
 * under ``studio.design.cv`` / ``studio.design.cover_letter``.
 *
 * Fetches the theme list from ``GET /api/v1/themes`` and the country
 * profile from ``GET /api/v1/country-profiles``. Design choices are NOT
 * stored by the backend — they live client-side only.
 *
 * @param {string} documentType  "cv" | "cover_letter" | "resignation"
 * @returns {{ design: {themeId, country, sidebar}, setDesign: function,
 *   themes: object[], countryProfile: object|null, themesLoading: boolean,
 *   countryLoading: boolean, fetchCountryProfile: function, isCv: boolean }}
 */
export function useDesignOptions(documentType) {
  const storageKey = `studio.design.${documentType}`;
  const [design, setDesignState] = useState(() => {
    try {
      const stored = window.localStorage.getItem(storageKey);
      if (stored) return JSON.parse(stored);
    } catch {}
    return { ...DEFAULT_DESIGN };
  });

  const [themes, setThemes] = useState([]);
  const [countryProfile, setCountryProfile] = useState(null);
  const [themesLoading, setThemesLoading] = useState(true);
  const [countryLoading, setCountryLoading] = useState(false);

  // Abort + stale-response guard for the country-profile fetch. Each request
  // bumps a counter and owns an AbortController; a response is only applied if
  // it is still the newest request (so a slow, superseded response can never
  // overwrite a newer country's profile).
  const countryAbortRef = useRef(null);
  const countryRequestRef = useRef(0);

  useEffect(() => () => countryAbortRef.current?.abort(), []);

  useEffect(() => {
    let isMounted = true;

    async function loadThemes() {
      setThemesLoading(true);
      try {
        const payload = await apiRequest('/api/v1/themes');
        if (isMounted) {
          setThemes(Array.isArray(payload.items) ? payload.items : []);
        }
      } catch {
        if (isMounted) setThemes([]);
      } finally {
        if (isMounted) setThemesLoading(false);
      }
    }

    loadThemes();
    return () => {
      isMounted = false;
    };
  }, []);

  const fetchCountryProfile = useCallback(async (country, language) => {
    // A new selection supersedes any in-flight request.
    countryAbortRef.current?.abort();
    if (!country) {
      setCountryProfile(null);
      setCountryLoading(false);
      return null;
    }
    const controller = new AbortController();
    countryAbortRef.current = controller;
    const requestId = ++countryRequestRef.current;
    setCountryLoading(true);
    try {
      const params = new URLSearchParams({
        country: toApiCountry(country),
        // Always send a language (the backend localises labels for it; BE
        // especially needs it). Never "undefined".
        language: language || 'en',
      });
      const payload = await apiRequest(`/api/v1/country-profiles?${params}`, {
        signal: controller.signal,
      });
      // Ignore stale responses: only the newest request may write state.
      if (requestId !== countryRequestRef.current) return null;
      setCountryProfile(payload);
      return payload;
    } catch (error) {
      // An abort (or a superseded request) is not an error worth surfacing.
      if (controller.signal.aborted || requestId !== countryRequestRef.current) {
        return null;
      }
      setCountryProfile(null);
      return null;
    } finally {
      if (requestId === countryRequestRef.current) setCountryLoading(false);
    }
  }, []);

  const setDesign = useCallback(
    (nextDesign) => {
      setDesignState(nextDesign);
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(nextDesign));
      } catch {}
    },
    [storageKey]
  );

  const isCv = documentType === 'cv';

  return {
    design,
    setDesign,
    themes,
    countryProfile,
    themesLoading,
    countryLoading,
    fetchCountryProfile,
    isCv,
  };
}
