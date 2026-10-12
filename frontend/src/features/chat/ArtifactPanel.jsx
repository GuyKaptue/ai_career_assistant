import React from 'react';
import { useI18n } from '../../i18n';
import { Button } from '../../components/ui/button';
import { XIcon } from '../../components/icons';

/**
 * Artifact preview (Claude Artifacts style). Shows the structured document the
 * assistant produced — a CV, cover letter or analysis report. Content is
 * rendered as plain text (never HTML).
 *
 * Wide screens (≥1024px): a split view docked beside the conversation.
 * Smaller screens: a full-screen sheet over the chat; X returns to it.
 */
export default function ArtifactPanel({ artifact, onClose }) {
  const { t } = useI18n();

  if (!artifact) return null;

  const title = artifact.title || artifact.document_type || t('chat.artifact');

  return (
    <aside
      className="fixed inset-0 z-[60] flex flex-col bg-background lg:static lg:inset-auto lg:z-auto lg:w-[min(44vw,40rem)] lg:shrink-0 lg:border-l lg:border-border"
      aria-label={t('chat.artifact')}
    >
      <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border px-4 pt-[env(safe-area-inset-top)]">
        <h2 className="truncate text-[15px] font-medium">{title}</h2>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t('chat.hideArtifact')}
          onClick={() => onClose?.()}
          className="h-8 w-8 text-muted-foreground"
        >
          <XIcon className="h-4 w-4" />
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {artifact.content ? (
          <pre className="whitespace-pre-wrap break-words rounded-2xl border border-border bg-card p-4 text-sm leading-relaxed">
            {artifact.content}
          </pre>
        ) : (
          <p className="my-8 text-center text-muted-foreground">{t('chat.artifact')}</p>
        )}
      </div>
      {artifact.review_before_sending && (
        <footer className="shrink-0 border-t border-border px-4 py-3">
          <p className="text-xs text-warning">{t('chat.reviewBeforeSending')}</p>
        </footer>
      )}
    </aside>
  );
}
