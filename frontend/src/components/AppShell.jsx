import React, {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { useI18n } from '../i18n';
import { ShellContext, useShell } from './shell-context';
import { useView } from '../hooks/useView';
import { cn } from '../lib/utils';
import SettingsDialog from './SettingsDialog';
import UserMenu from './UserMenu';
import { Button } from './ui/button';
import {
  BriefcaseIcon,
  ClipboardCheckIcon,
  FileTextIcon,
  KanbanIcon,
  MessageIcon,
  PanelLeftIcon,
  PlusIcon,
  XIcon,
} from './icons';
import { BrandMark } from './brand/BrandMark';
import { useAuthDialog } from '../hooks/useAuthDialog';
import { useSession } from '../hooks/useSession';
import { useSettingsDialog } from '../hooks/useSettingsDialog';

/** Below this width the sidebar becomes a slide-in drawer (Claude uses md). */
const MOBILE_QUERY = '(max-width: 767px)';
const COLLAPSE_STORAGE_KEY = 'aca-sidebar-collapsed';

const VIEW_ICONS = {
  chat: MessageIcon,
  documents: FileTextIcon,
  'resume-checker': ClipboardCheckIcon,
  jobs: BriefcaseIcon,
  tracker: KanbanIcon,
};

/** Tracks a CSS media query reactively (drawer vs. persistent sidebar). */
function useMediaQuery(query) {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(query).matches
      : false,
  );

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const list = window.matchMedia(query);
    const onChange = (event) => setMatches(event.matches);
    setMatches(list.matches);
    list.addEventListener('change', onChange);
    return () => list.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}

function readCollapsed() {
  try {
    return window.localStorage.getItem(COLLAPSE_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

/**
 * Claude-style application shell, shared by every workspace.
 *
 *   ┌───────────────┬──────────────────────────────────────┐
 *   │ brand   [⟨]   │  header (toggle · title · sign in)   │
 *   │ + New chat    ├──────────────────────────────────────┤
 *   │ nav links     │                                      │
 *   │ {sidebar      │             main content             │
 *   │  content}     │                                      │
 *   │ account row   │                                      │
 *   └───────────────┴──────────────────────────────────────┘
 *
 * - ≥ 768px: persistent 288px sidebar, collapsible (choice is remembered)
 * - < 768px: the sidebar is a drawer with a backdrop; it closes on Escape, on
 *   backdrop tap and after navigating
 * - This component owns the ONE Settings dialog of the app. The only way to
 *   open it is the account menu at the bottom of the sidebar.
 *
 * `sidebarContent` may be a node or a function receiving `{ closeDrawer }`,
 * rendered in the scrollable middle section of the sidebar.
 */
export { useShell };

export default function AppShell({ sidebarContent, onNewChat, children }) {
  const { t } = useI18n();
  const { view, setView, views } = useView();
  const { isOpen: settingsOpen, closeSettings } = useSettingsDialog();

  const isMobile = useMediaQuery(MOBILE_QUERY);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);

  // The drawer only exists on small screens; drop stale state on breakpoint change.
  useEffect(() => {
    if (!isMobile) setDrawerOpen(false);
  }, [isMobile]);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  // Escape closes the drawer.
  useEffect(() => {
    if (!drawerOpen) return undefined;
    function onKeyDown(event) {
      if (event.key === 'Escape') closeDrawer();
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [drawerOpen, closeDrawer]);

  const toggleSidebar = useCallback(() => {
    if (isMobile) {
      setDrawerOpen((open) => !open);
      return;
    }
    setCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(COLLAPSE_STORAGE_KEY, next ? '1' : '0');
      } catch {
        // Storage unavailable (private mode); the toggle still works for this session.
      }
      return next;
    });
  }, [isMobile]);

  const sidebarOpen = isMobile ? drawerOpen : !collapsed;
  const sidebarHidden = !sidebarOpen;

  const shell = useMemo(
    () => ({ isMobile, sidebarOpen, toggleSidebar, closeDrawer }),
    [isMobile, sidebarOpen, toggleSidebar, closeDrawer],
  );

  function handleNewChat() {
    if (view !== 'chat') setView('chat');
    onNewChat?.();
    closeDrawer();
  }

  function handleNavigate(id) {
    setView(id);
    closeDrawer();
  }

  return (
    <ShellContext.Provider value={shell}>
      <div className="flex h-dvh max-h-dvh overflow-hidden bg-background text-foreground">
        {/* Drawer backdrop (small screens) */}
        {isMobile && drawerOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/45 backdrop-blur-[2px]"
            onClick={closeDrawer}
            aria-hidden="true"
            data-testid="drawer-backdrop"
          />
        )}

        <aside
          aria-label={t('chat.sidebar', 'Sidebar')}
          // `inert` takes the closed sidebar out of the tab order and the a11y tree.
          inert={sidebarHidden ? '' : undefined}
          className={cn(
            'z-50 flex shrink-0 flex-col overflow-hidden border-sidebar-foreground/0 bg-sidebar text-sidebar-foreground',
            'transition-[transform,width] duration-200 ease-out',
            isMobile
              ? cn(
                  'fixed inset-y-0 left-0 w-[min(86vw,20rem)] border-r border-border shadow-strong',
                  drawerOpen ? 'translate-x-0' : '-translate-x-full',
                )
              : cn('relative h-full border-r border-border', collapsed ? 'w-0 border-r-0' : 'w-72'),
          )}
        >
          <div className="flex h-full min-h-0 w-[min(86vw,20rem)] flex-col md:w-72">
            {/* Brand + collapse */}
            <div className="flex h-12 shrink-0 items-center justify-between gap-2 pl-4 pr-2">
              <div className="flex min-w-0 items-center gap-2">
                <BrandMark variant="glyph" size={20} className="shrink-0 text-primary" />
                <span className="truncate font-serif text-xl leading-none tracking-tight text-foreground">
                  {t('app.title')}
                </span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={isMobile ? closeDrawer : toggleSidebar}
                className="h-8 w-8 text-muted-foreground"
                aria-label={t('chat.closeSidebar', 'Close sidebar')}
              >
                {isMobile ? <XIcon className="h-4 w-4" /> : <PanelLeftIcon className="h-[18px] w-[18px]" />}
              </Button>
            </div>

            {/* Primary action + workspace navigation */}
            <div className="shrink-0 space-y-0.5 px-2 pb-2 pt-1">
              <button
                type="button"
                onClick={handleNewChat}
                className="group flex h-9 w-full items-center gap-2.5 rounded-lg px-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
              >
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  <PlusIcon className="h-3.5 w-3.5" />
                </span>
                <span className="truncate">{t('chat.newChat', 'New chat')}</span>
              </button>

              <nav aria-label={t('nav.sections', 'Workspaces')} className="space-y-0.5">
                {views.map((entry) => {
                  const Icon = VIEW_ICONS[entry.id] || MessageIcon;
                  const active = view === entry.id;
                  return (
                    <button
                      key={entry.id}
                      type="button"
                      onClick={() => handleNavigate(entry.id)}
                      aria-current={active ? 'page' : undefined}
                      title={t(entry.descriptionKey, '')}
                      className={cn(
                        'flex h-9 w-full items-center gap-2.5 rounded-lg px-2 text-left text-sm transition-colors',
                        active
                          ? 'bg-accent font-medium text-foreground'
                          : 'text-sidebar-foreground hover:bg-accent hover:text-foreground',
                      )}
                    >
                      <Icon className="h-[18px] w-[18px] shrink-0" />
                      <span className="truncate">{t(entry.i18nKey)}</span>
                    </button>
                  );
                })}
              </nav>
            </div>

            {/* Scrollable section supplied by the workspace (search, projects, recents) */}
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {typeof sidebarContent === 'function' ? sidebarContent({ closeDrawer }) : sidebarContent}
            </div>

            {/* Account row — the single entry point to Settings */}
            <div className="shrink-0 border-t border-border p-2">
              <UserMenu />
            </div>
          </div>
        </aside>

        {/* Main column */}
        <div className="flex h-full min-w-0 flex-1 flex-col">{children}</div>

        {/* The one and only Settings dialog */}
        <SettingsDialog open={settingsOpen} onOpenChange={(next) => !next && closeSettings()} />
      </div>
    </ShellContext.Provider>
  );
}

/** Sign-in / sign-up buttons shown to guests, like claude.ai's logged-out header. */
function HeaderAuth() {
  const { t } = useI18n();
  const { session, authLoading } = useSession();
  const { openAuth } = useAuthDialog();

  if (authLoading || session) return null;

  return (
    <div className="flex items-center gap-1.5">
      <Button variant="ghost" size="sm" onClick={() => openAuth('sign-in')}>
        {t('auth.signIn')}
      </Button>
      <Button size="sm" className="hidden sm:inline-flex" onClick={() => openAuth('sign-up')}>
        {t('auth.signUp')}
      </Button>
    </div>
  );
}

/**
 * Top bar shared by every workspace: sidebar toggle (only when the sidebar is
 * hidden), the page / conversation title, optional extra controls and the
 * guest sign-in buttons.
 */
export function ShellHeader({ title, titleTag: TitleTag = 'h1', children, className }) {
  const { t } = useI18n();
  const { isMobile, sidebarOpen, toggleSidebar } = useShell();
  const showToggle = isMobile || !sidebarOpen;

  return (
    <header
      className={cn(
        'flex h-12 shrink-0 items-center gap-1 px-2 pt-[env(safe-area-inset-top)] sm:gap-2 sm:px-3',
        className,
      )}
    >
      {showToggle && (
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleSidebar}
          className="h-9 w-9 shrink-0 text-muted-foreground"
          aria-label={t('chat.openSidebar', 'Open sidebar')}
          aria-expanded={sidebarOpen}
        >
          <PanelLeftIcon className="h-[18px] w-[18px]" />
        </Button>
      )}

      <TitleTag
        className="min-w-0 flex-1 truncate px-1 text-[15px] font-medium text-foreground"
        title={typeof title === 'string' ? title : undefined}
      >
        {title}
      </TitleTag>

      <div className="flex shrink-0 items-center gap-1.5">
        {children}
        <HeaderAuth />
      </div>
    </header>
  );
}
