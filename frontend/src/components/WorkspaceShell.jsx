import React from 'react';

import { useI18n } from '../i18n';
import AppShell, { ShellHeader } from './AppShell';

/**
 * Shell for every workspace other than chat (documents, resume checker, jobs,
 * tracker). It uses the same Claude-style sidebar, account menu and single
 * Settings dialog as the chat, so navigation never dead-ends and the frame
 * looks identical everywhere.
 */
export default function WorkspaceShell({ titleKey, children }) {
  const { t } = useI18n();

  return (
    <AppShell>
      <ShellHeader title={t(titleKey)} />
      <main className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 pb-8 pt-2 sm:px-6 lg:px-8">
        <div className="mx-auto w-full max-w-6xl">{children}</div>
      </main>
    </AppShell>
  );
}
