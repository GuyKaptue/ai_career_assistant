import React, { useMemo } from 'react';
import { useI18n } from '../../i18n';
import { debugLog } from '../../lib/debug';
import { cn } from '../../lib/utils';
import { FolderIcon } from '../../components/icons';

/**
 * Sidebar — project shortcuts and conversation history.
 *
 * Structure:
 * - Project tiles: each opens a dedicated chat workspace (a backend session
 *   mode such as interview prep or ATS review) instead of a bare chat.
 * - Recent conversations: grouped by time, each row showing the title and
 *   the last-update date, with an inset accent bar on the active one.
 * - Settings/account live in the rail footer (see ChatLayout).
 */

/** Group sessions by time for organization */
export function groupSessionsByTime(sessions, now = new Date()) {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const oneDay = 24 * 60 * 60 * 1000;
  const startOfYesterday = startOfToday - oneDay;
  const startOfWeek = startOfToday - 6 * oneDay;

  const buckets = { today: [], yesterday: [], previous7Days: [], older: [] };
  for (const session of sessions) {
    const updated = new Date(session.updated_at || session.created_at || now).getTime();
    if (Number.isNaN(updated)) {
      buckets.older.push(session);
    } else if (updated >= startOfToday) {
      buckets.today.push(session);
    } else if (updated >= startOfYesterday) {
      buckets.yesterday.push(session);
    } else if (updated >= startOfWeek) {
      buckets.previous7Days.push(session);
    } else {
      buckets.older.push(session);
    }
  }
  return buckets;
}

const PROJECT_ITEMS = [
  { key: 'careerCoaching', label: 'Career Coaching', mode: 'general' },
  { key: 'resumeReview', label: 'Resume Review', mode: 'ats_checker' },
  { key: 'interviewPrep', label: 'Interview Prep', mode: 'interview_prep' },
  { key: 'jobSearch', label: 'Job Search', mode: 'job_search' },
];

const SECTION_LABEL = 'px-2 pb-1 text-xs font-medium text-muted-foreground';

export default function Sidebar({
  session,
  sessions = [],
  activeSessionId = null,
  onSelectSession,
  onNewChat,
  onOpenProject,
  onOpenSettings,
  onDeleteSession,
  searchQuery = '',
  onCloseMobileSidebar,
}) {
  const { t } = useI18n();

  function handleSelect(id) {
    debugLog('chat', 'select session', { id });
    onSelectSession?.(id);
    onCloseMobileSidebar?.();
  }

  const query = searchQuery.toLowerCase();
  const filteredSessions = sessions.filter(
    (sessionItem) =>
      sessionItem.title?.toLowerCase().includes(query) || sessionItem.id?.toLowerCase().includes(query),
  );

  const filteredGrouped = useMemo(() => groupSessionsByTime(filteredSessions), [filteredSessions]);

  const bucketsToShow = [
    { key: 'today', label: t('chat.today'), items: filteredGrouped.today },
    { key: 'yesterday', label: t('chat.yesterday'), items: filteredGrouped.yesterday },
    { key: 'previous7Days', label: t('chat.previous7Days'), items: filteredGrouped.previous7Days },
    { key: 'older', label: t('chat.older'), items: filteredGrouped.older },
  ].filter((bucket) => bucket.items.length > 0);

  // Which project matches the open conversation (drives the active style).
  const activeSession = sessions.find((item) => item.id === activeSessionId);
  const activeProjectMode = activeSession?.mode ?? null;

  function handleOpenProject(project) {
    debugLog('chat', 'open project', { project: project.key, mode: project.mode });
    onOpenProject?.(project);
    onCloseMobileSidebar?.();
  }

  return (
    <div className="flex flex-col gap-4 px-2 pb-3 pt-1">
      {/* Projects — each opens a dedicated chat workspace */}
      <section>
        <h2 className={SECTION_LABEL}>{t('chat.projects')}</h2>
        <div className="chat-projects space-y-0.5">
          {PROJECT_ITEMS.map((project) => {
            const isActive = activeProjectMode === project.mode;
            const label = t(`chat.project.${project.key}`, project.label);
            return (
              <button
                key={project.key}
                type="button"
                onClick={() => handleOpenProject({ ...project, label: project.label })}
                aria-pressed={isActive}
                title={`${t('chat.openProject', 'Open project')}: ${label}`}
                className={cn(
                  'flex h-8 w-full items-center gap-2.5 rounded-lg px-2 text-left text-sm transition-colors',
                  isActive
                    ? 'bg-accent font-medium text-foreground'
                    : 'text-sidebar-foreground hover:bg-accent hover:text-foreground',
                )}
              >
                <FolderIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="truncate">{label}</span>
              </button>
            );
          })}
        </div>
      </section>

      {/* Recents */}
      <section>
        <h2 className={SECTION_LABEL}>{t('chat.recentConversations')}</h2>

        {bucketsToShow.length === 0 ? (
          <p className="px-2 py-2 text-sm text-muted-foreground">
            {searchQuery ? t('chat.noMatchingConversations') : t('chat.noConversationsYet')}
          </p>
        ) : (
          bucketsToShow.map((bucket) => (
            <div key={bucket.key} className="mb-2">
              <div className="px-2 pb-0.5 pt-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground/80">
                {bucket.label}
              </div>
              <div className="space-y-0.5">
                {bucket.items.map((sessionItem) => {
                  const isActive = sessionItem.id === activeSessionId;
                  return (
                    <button
                      key={sessionItem.id}
                      type="button"
                      onClick={() => handleSelect(sessionItem.id)}
                      aria-current={isActive ? 'true' : undefined}
                      title={sessionItem.title}
                      className={cn(
                        'flex h-8 w-full items-center rounded-lg px-2 text-left text-sm transition-colors',
                        isActive
                          ? 'bg-accent font-medium text-foreground'
                          : 'text-sidebar-foreground hover:bg-accent hover:text-foreground',
                      )}
                    >
                      <span className="truncate">{sessionItem.title || t('chat.newChat')}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  );
}
