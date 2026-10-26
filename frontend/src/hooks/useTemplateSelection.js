import { useState, useEffect, useCallback, useMemo } from 'react';

const DEFAULT_TEMPLATE_ID = {
  cv: 'professional',
  cover_letter: 'classic-letter',
  resignation: 'formal-resignation',
};

/**
 * Persists the selected template id per document type in localStorage
 * under ``studio.template.cv`` / ``studio.template.cover_letter``.
 *
 * Validates the stored id against the fetched template list; falls back
 * to the default (professional / classic-letter) when invalid, and does
 * not persist the invalid id. Revalidates when templates, locale, or
 * session change (covers login/logout and locale change).
 *
 * @param {string} documentType  "cv" | "cover_letter" | "resignation"
 * @param {import('../types').Template[]} templates  fetched template list
 * @param {string} locale  current i18n locale
 * @returns {{ selectedId: string, setSelectedId: function, isValidated: boolean }}
 */
export function useTemplateSelection(documentType, templates, locale) {
  const storageKey = `studio.template.${documentType}`;
  const defaultId = DEFAULT_TEMPLATE_ID[documentType] || 'professional';

  const [selectedId, setSelectedIdState] = useState(() => {
    try {
      const stored = window.localStorage.getItem(storageKey);
      if (stored) return stored;
    } catch {}
    return defaultId;
  });

  const validIds = useMemo(
    () => new Set(templates.map((t) => t.id)),
    [templates]
  );
  const isValid = useMemo(() => validIds.has(selectedId), [
    selectedId,
    validIds,
  ]);

  // Revalidate when templates or locale change (covers login/logout,
  // locale change, and failed-fetch scenarios).
  useEffect(() => {
    if (!isValid) {
      const next = defaultId;
      setSelectedIdState(next);
      try {
        window.localStorage.setItem(storageKey, next);
      } catch {}
    }
  }, [templates, locale, storageKey, defaultId, isValid]);

  const setSelectedId = useCallback(
    (nextId) => {
      setSelectedIdState(nextId);
      try {
        window.localStorage.setItem(storageKey, nextId);
      } catch {}
    },
    [storageKey]
  );

  return { selectedId, setSelectedId, isValidated: isValid };
}
