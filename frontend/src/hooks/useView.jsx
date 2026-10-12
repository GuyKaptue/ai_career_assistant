import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  BriefcaseIcon,
  ClipboardCheckIcon,
  FileTextIcon,
  KanbanIcon,
  MessageIcon,
} from '../components/icons';

const VIEW_STORAGE_KEY = 'aca-view';

/**
 * Views available from the workspace. Each id maps to a page component in
 * App.jsx; the label/icon/i18n key drives the settings navigation menu.
 *
 * `Icon` holds the shared stroke-icon component (same set the sidebar renders)
 * rather than an emoji, so any future consumer stays visually consistent and
 * theme-aware.
 */
export const VIEWS = [
  { id: 'chat', i18nKey: 'nav.chat', Icon: MessageIcon, descriptionKey: 'nav.chatDescription' },
  { id: 'documents', i18nKey: 'nav.documents', Icon: FileTextIcon, descriptionKey: 'nav.documentsDescription' },
  { id: 'resume-checker', i18nKey: 'nav.resumeChecker', Icon: ClipboardCheckIcon, descriptionKey: 'nav.resumeCheckerDescription' },
  { id: 'jobs', i18nKey: 'nav.jobs', Icon: BriefcaseIcon, descriptionKey: 'nav.jobsDescription' },
  { id: 'tracker', i18nKey: 'nav.tracker', Icon: KanbanIcon, descriptionKey: 'nav.trackerDescription' },
];

const ViewContext = createContext({
  view: 'chat',
  setView: () => {},
  views: VIEWS,
});

function readStoredView() {
  if (typeof window === 'undefined') return 'chat';
  try {
    const stored = window.localStorage.getItem(VIEW_STORAGE_KEY);
    return VIEWS.some((v) => v.id === stored) ? stored : 'chat';
  } catch {
    // Storage unavailable (private mode) — fall back to chat.
    return 'chat';
  }
}

/**
 * Active-workspace navigation.
 *
 * The chat page is the default view; the other career-assistant tools are
 * reachable from the sidebar Settings menu. The choice is persisted so a
 * reload keeps the user where they were.
 */
export function ViewProvider({ children }) {
  const [view, setViewState] = useState(readStoredView);

  useEffect(() => {
    try {
      window.localStorage.setItem(VIEW_STORAGE_KEY, view);
    } catch {
      // Storage unavailable; navigation still works for this session.
    }
  }, [view]);

  const setView = useCallback((next) => {
    setViewState(VIEWS.some((v) => v.id === next) ? next : 'chat');
  }, []);

  const value = useMemo(
    () => ({ view, setView, views: VIEWS }),
    [view, setView],
  );

  return <ViewContext.Provider value={value}>{children}</ViewContext.Provider>;
}

export function useView() {
  return useContext(ViewContext);
}
