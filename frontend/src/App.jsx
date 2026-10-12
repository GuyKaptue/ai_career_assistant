import React from 'react';

import Chat from './features/chat/Chat';
import DocumentsPage from './pages/DocumentsPage';
import JobsPage from './pages/JobsPage';
import ResumeCheckerPage from './pages/ResumeCheckerPage';
import TrackerPage from './pages/TrackerPage';
import { useSession } from './hooks/useSession';
import { useView } from './hooks/useView';

/**
 * Application shell.
 *
 * Chat is the default workspace. The other career-assistant tools are reached
 * from the sidebar navigation (see components/AppShell.jsx), which sets the
 * active view here. The choice is persisted by ViewProvider so a reload keeps
 * the user in the same workspace.
 */
export default function App() {
  const { session } = useSession();
  const { view } = useView();

  return (
    <>
      {view === 'chat' && <Chat session={session} />}
      {view === 'documents' && <DocumentsPage />}
      {view === 'resume-checker' && <ResumeCheckerPage />}
      {view === 'jobs' && <JobsPage />}
      {view === 'tracker' && <TrackerPage />}
    </>
  );
}
