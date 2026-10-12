import React, { useCallback } from 'react';
import { useSession } from '../hooks/useSession';
import { useChat } from '../hooks/useChat';
import { useI18n } from '../i18n';
import { useStatus } from '../hooks/useStatus.jsx';
import AppShell from './AppShell';
import Sidebar from '../features/chat/Sidebar';
import ChatHeader from '../features/chat/ChatHeader';
import ChatBox from '../features/chat/ChatBox';
import { Input } from './ui/input';
import { SearchIcon } from './icons';

/**
 * Workspace mode → the backend routing task used for auto-selection.
 * Mirrors MODE_TASKS in backend/app/domain/chat/models.py.
 */
const MODE_TASKS = {
  general: 'career_advice',
  cv_builder: 'cv_generation',
  cover_letter: 'cover_letter_generation',
  ats_checker: 'ats_analysis',
  job_search: 'job_matching',
  interview_prep: 'career_advice',
};

/**
 * Chat workspace.
 *
 * The Claude-style frame (sidebar / drawer, account menu, the single Settings
 * dialog) comes from AppShell; this component supplies the chat-specific
 * sidebar section (search, projects, recents), the header and the transcript +
 * composer. Chat state (sessions, messages, completions) is owned by useChat,
 * which talks to the real /api/v1/chat endpoints.
 */
export default function ChatLayout({ session: sessionProp }) {
  const { session } = useSession();
  const { t } = useI18n();
  const { report } = useStatus();
  const chat = useChat(session);
  const activeUser = sessionProp ?? session;

  /**
   * Open a project as a dedicated chat workspace. Each project maps to one of
   * the backend session modes, so the assistant is primed for that workflow.
   * Guests get a local workspace; signed-in users get a persisted session.
   */
  const openProject = useCallback(
    async (project) => {
      const mode = project?.mode || 'general';
      const title = project?.label ? `${project.label}` : t('chat.newChat');

      if (activeUser) {
        const created = await chat.createSession({ title, mode });
        if (created) {
          report(t('status.projectOpened', 'Project opened'), title);
        }
        return created;
      }

      chat.newChat();
      report(t('status.guestProjectOpened', 'Guest workspace'), title);
      return null;
    },
    [activeUser, chat, t, report],
  );

  // Router task implied by the open session's workspace mode — biases auto model selection.
  const activeSession = chat.sessions.find((item) => item.id === chat.activeSessionId) || null;
  const activeTask = MODE_TASKS[activeSession?.mode] || 'career_advice';

  return (
    <AppShell
      onNewChat={chat.newChat}
      sidebarContent={({ closeDrawer }) => (
        <>
          <div className="px-2 pb-2">
            <div className="relative">
              <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="search"
                value={chat.searchQuery}
                onChange={(event) => chat.setSearchQuery(event.target.value)}
                placeholder={t('chat.searchConversations')}
                className="h-9 border-transparent bg-accent/60 pl-9 pr-3 text-sm"
                aria-label={t('chat.searchConversations')}
              />
            </div>
          </div>
          <Sidebar
            session={session}
            sessions={chat.sessions}
            activeSessionId={chat.activeSessionId}
            searchQuery={chat.searchQuery}
            onSelectSession={chat.selectSession}
            onNewChat={chat.newChat}
            onOpenProject={openProject}
            onDeleteSession={chat.deleteSession}
            onCloseMobileSidebar={closeDrawer}
          />
        </>
      )}
    >
      <ChatHeader activeSessionId={chat.activeSessionId} sessions={chat.sessions} />

      <main className="min-h-0 flex-1 overflow-hidden">
        <ChatBox
          session={activeUser}
          task={activeTask}
          activeSessionId={chat.activeSessionId}
          messages={chat.messages}
          sending={chat.sending}
          loading={chat.loading}
          error={chat.error}
          onSendMessage={chat.sendMessage}
          onStopGeneration={chat.stopGeneration}
          onNewChat={chat.newChat}
          onCreateSession={chat.createSession}
        />
      </main>
    </AppShell>
  );
}
