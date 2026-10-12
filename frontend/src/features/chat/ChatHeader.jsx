import React from 'react';
import { useI18n } from '../../i18n';
import { ShellHeader } from '../../components/AppShell';

/**
 * Chat top bar — sidebar toggle (when the sidebar is hidden), the open
 * conversation's title and, for guests, the sign-in buttons (all supplied by
 * ShellHeader). The model picker lives in the composer, like claude.ai.
 */
export default function ChatHeader({ sessions = [], activeSessionId = null }) {
  const { t } = useI18n();
  const activeSession = sessions.find((item) => item.id === activeSessionId) || null;

  return <ShellHeader titleTag="h2" title={activeSession?.title || t('chat.newChat')} />;
}
