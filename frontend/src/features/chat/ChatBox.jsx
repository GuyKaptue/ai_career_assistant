import React, { useState, useRef, useEffect } from 'react';
import { useI18n } from '../../i18n';
import { useSession } from '../../hooks/useSession';
import { useStatus } from '../../hooks/useStatus.jsx';
import { useGuestMessages } from '../../hooks/useGuestMessages';
import { AUTO_MODEL, useModels } from '../../hooks/useModels';
import { apiUpload } from '../../lib/api';
import { debugLog } from '../../lib/debug';
import ChatCanvas from './ChatCanvas';
import PromptBox from './PromptBox';
import { detectJobUrl, detectJobText, quickActions } from './inputHints';
import ArtifactPanel from './ArtifactPanel';
import { useAuthDialog } from '../../hooks/useAuthDialog';
import { Button } from '../../components/ui/button';
import { Select } from '../../components/ui/select';
import { BrandMark } from '../../components/brand/BrandMark';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../components/ui/dialog';

const GUEST_MESSAGE_LIMIT = 5;

/**
 * Starter cards shown on the empty state. Clicking one sends the prompt
 * straight away (same behaviour as our UI reference) instead of only
 * pre-filling the composer.
 */
const STARTER_PROMPTS = [
  {
    titleKey: 'chat.suggestedPrompt1',
    subKey: 'chat.suggestedPrompt1Sub',
    subFallback: 'Tailor your CV to a specific role.',
  },
  {
    titleKey: 'chat.suggestedPrompt2',
    subKey: 'chat.suggestedPrompt2Sub',
    subFallback: 'A letter matched to the job ad.',
  },
  {
    titleKey: 'chat.suggestedPrompt3',
    subKey: 'chat.suggestedPrompt3Sub',
    subFallback: 'How to prepare and what to expect.',
  },
  {
    titleKey: 'chat.suggestedPrompt4',
    subKey: 'chat.suggestedPrompt4Sub',
    subFallback: 'Score a CV against a job description.',
  },
];

/**
 * ChatBox — main workspace.
 *
 * Area A: welcome screen or conversation transcript
 * Area B: composer (message + optional CV attachment)
 * Area C: optional artifact preview rendered side-by-side on wide screens
 *
 * Message state is owned by useChat (via ChatLayout) so the transcript,
 * session history and composer never disagree. This component owns only
 * composer-local concerns: drafts, attachments, guest limits, modals.
 */
export default function ChatBox({
  session,
  activeSessionId,
  messages = [],
  sending = false,
  loading = false,
  error = null,
  onSendMessage,
  onNewChat,
  onCreateSession,
  onStopGeneration,
  task = null,
}) {
  const { t, locale } = useI18n();
  const { report } = useStatus();
  const { session: authSession } = useSession();
  const activeUser = session ?? authSession;
  const { count, hasReachedLimit, increment, reset } = useGuestMessages();
  const { models, selectedModel, setSelectedModel, autoDefaultModel, loading: modelsLoading } = useModels(activeUser, task);
  const { openAuth } = useAuthDialog();

  const [input, setInput] = useState('');
  const [attachment, setAttachment] = useState(null);
  const [attaching, setAttaching] = useState(false);
  const [showLoginPrompt, setShowLoginPrompt] = useState(false);
  const [treatAsPlainText, setTreatAsPlainText] = useState(false);

  const jobUrlDetected = !treatAsPlainText && detectJobUrl(input);
  const jobTextDetected = !treatAsPlainText && detectJobText(input);

  const threadRef = useRef(null);
  const inputRef = useRef(null);

  const hasMessages = messages.length > 0;
  const lastAssistantMessage = [...messages].reverse().find((m) => m.role === 'assistant');
  // The preview follows the latest assistant artifact. Closing it remembers
  // *which* message it belonged to, so it stays closed until a new one arrives
  // (it used to re-open instantly because the fallback re-derived it).
  const artifactKey = lastAssistantMessage?.id ?? lastAssistantMessage?.created_at ?? messages.length;
  const artifact = lastAssistantMessage?.artifact && dismissedArtifactKey !== artifactKey
    ? lastAssistantMessage.artifact
    : null;

  // Follow the transcript as new messages arrive.
  useEffect(() => {
    const node = threadRef.current;
    if (!node) return undefined;
    node.scrollTop = node.scrollHeight;
  }, [messages.length, sending]);

  // Guest counters are per-anonymous-visit; reset them once the user signs in.
  useEffect(() => {
    if (activeUser) {
      reset();
    }
  }, [activeUser, reset]);

  // Keyboard shortcut: Cmd/Ctrl+K focuses the composer.
  useEffect(() => {
    function onKeyDown(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const renderedMessages = messages.filter((m) => m.role === 'user' || m.role === 'assistant');

  /** Sends `text` as a new turn (shared by the composer, starters and retry). */
  async function sendText(text) {
    const outgoing = text.trim();
    if ((!outgoing && !attachment) || sending || attaching) return;

    // Guest message limit — the backend requires auth for persistent chat.
    if (!activeUser) {
      const allowed = increment();
      if (!allowed) {
        setShowLoginPrompt(true);
        return;
      }
    }

    const message = attachment?.text ? `${attachment.text}\n\n---\n\n${outgoing}`.trim() : outgoing;
    // Remember the guest's draft so it can be restored if the send cannot be served.
    const draftInput = input;
    const draftAttachment = attachment;
    setInput('');
    setAttachment(null);

    try {
      // 'auto' means "let the router pick per task" — send no model_id so the
      // backend's auto-selection runs instead of pinning a literal model.
       const preferredModel = selectedModel === AUTO_MODEL ? null : selectedModel;
       const result = await onSendMessage?.(message, preferredModel, {
         document_context: attachment?.text || '',
         preferences: treatAsPlainText ? { treat_as_plain_text: true } : undefined,
       });
       setTreatAsPlainText(false);
       if (!result) {
        if (activeUser) {
          report(t('chat.unableToSend'), error || t('chat.retryLater'));
        } else {
          // Chat completions are JWT-gated server-side (POST /api/v1/chat/
          // completions answers 401 without a token), so a guest message can
          // never reach a reply. Keep the typed draft and open the existing
          // sign-in dialog instead of silently dropping the message.
          setInput(draftInput);
          setAttachment(draftAttachment);
          setShowLoginPrompt(true);
        }
      }
      return result;
    } catch (err) {
      debugLog('chat', 'send failed', { message: err?.message });
      report(t('chat.unableToSend'), err?.message || '');
      return null;
    }
  }

  function handleSend() {
    return sendText(input);
  }

  /**
   * Re-sends the last user prompt as a fresh turn. The previous answer stays
   * in the transcript — we do not delete server-side history on retry.
   */
  async function handleRetry() {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    if (!lastUser?.content) return;
    await sendText(lastUser.content);
  }

  async function handleAttach(file) {
    setAttaching(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const result = await apiUpload('/api/v1/resume/extract', {
        session: activeUser,
        formData,
      });
      setAttachment({ name: file.name, text: result?.text || '' });
      report(t('chat.extractedFrom', { filename: file.name }));
      inputRef.current?.focus();
    } catch (err) {
      debugLog('chat', 'attachment extract failed', { filename: file.name, message: err?.message });
      report(t('chat.unableToReadFile', { filename: file.name }), err?.message || '');
    } finally {
      setAttaching(false);
    }
  }

  const remaining = !activeUser ? Math.max(0, GUEST_MESSAGE_LIMIT - count) : null;

  const modelPicker = (
    <Select
      value={selectedModel ?? AUTO_MODEL}
      onChange={(event) => setSelectedModel(event.target.value || null)}
      disabled={modelsLoading || models.length === 0}
      aria-label={t('chat.model')}
      className="h-8 w-auto min-w-0 max-w-[9.5rem] shrink truncate border-transparent bg-transparent px-2 text-xs text-muted-foreground hover:bg-accent @md:max-w-[16rem]"
    >
      <option value={AUTO_MODEL}>
        {autoDefaultModel ? `${t('chat.modelAuto')} · ${autoDefaultModel}` : t('chat.modelAuto')}
      </option>
      {models.map((model) => (
        <option key={model.model_id} value={model.model_id}>
          {model.model_id}
        </option>
      ))}
    </Select>
  );

  return (
    <div className="flex h-full min-h-0 bg-background">
      {/* Conversation column: transcript + composer */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Transcript (only once there is something to show) */}
        <div
          ref={threadRef}
          className={hasMessages || loading ? 'min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-6 sm:px-6' : 'hidden'}
          aria-live="polite"
          aria-busy={sending}
        >
          <div className="chat-thread mx-auto w-full max-w-3xl">
            {hasMessages && <ChatCanvas messages={renderedMessages} sending={sending} onRetry={handleRetry} onSendText={sendText} session={activeUser} />}
            {!hasMessages && loading && (
              <p className="text-center text-sm text-muted-foreground" role="status">
                {t('chat.loadingHistory', 'Loading conversation…')}
              </p>
            )}
          </div>
        </div>

        {/* Composer zone: centred under the greeting on a new chat, docked at the bottom otherwise */}
        <div
          className={
            hasMessages || loading
              ? 'shrink-0 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-6'
              : 'flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto px-4 pb-[8vh] sm:px-6'
          }
        >
          {!hasMessages && !loading && (
            <section className="chat-welcome mb-6 w-full max-w-2xl text-center sm:mb-8">
              <div className="flex flex-col items-center justify-center gap-2 sm:flex-row sm:gap-3">
                <BrandMark variant="glyph" size={32} className="h-8 w-8 shrink-0 text-primary sm:h-9 sm:w-9" />
                <h1 className="font-serif text-3xl font-normal leading-tight tracking-tight text-foreground text-balance sm:text-[2.5rem]">
                  {t('chat.welcomeHeadlineA', 'What are we')}
                  <em className="text-primary"> {t('chat.welcomeHeadlineAccent', 'working on')}</em>
                  {t('chat.welcomeHeadlineEnd', ' today?')}
                </h1>
              </div>
              <p className="mx-auto mt-3 max-w-xl text-muted-foreground">
                {t('chat.welcomeSubtitle', 'Pick a starting point or type your own message below.')}
              </p>
            </section>
          )}

          <div className="chat-composer w-full max-w-3xl">
            {/* Guest counter warning */}
            {remaining !== null && remaining <= 2 && remaining > 0 && (
              <p className="mb-2 rounded-xl bg-warning/10 px-4 py-2 text-center text-sm text-warning dark:text-warning" role="status">
                {t('chat.guestMessagesRemaining', { count: remaining })}
              </p>
            )}

            {/* Error feedback */}
            {error && (
              <p className="mb-2 rounded-xl bg-destructive/10 px-4 py-2 text-center text-sm text-destructive" role="alert">
                {error}
              </p>
            )}

            {/* Detection chips */}
            {(jobUrlDetected || jobTextDetected) && (
              <div className="mb-2 flex flex-wrap gap-2" role="status" aria-live="polite">
                {jobUrlDetected && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1 text-xs">
                    {t('chat.jobLinkDetected')}
                    <button type="button" aria-label={t('chat.dismissChip')} onClick={() => setTreatAsPlainText(true)}>✕</button>
                  </span>
                )}
                {jobTextDetected && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1 text-xs">
                    {t('chat.jobDescriptionDetected')}
                    <button type="button" aria-label={t('chat.dismissChip')} onClick={() => setTreatAsPlainText(true)}>✕</button>
                  </span>
                )}
              </div>
            )}

            {/* CV status */}
            <div className="mb-2 text-xs text-muted-foreground">
              {attachment ? `${t('chat.cvAttached')}: ${attachment.name}` : t('chat.noCvAttached')}
            </div>

            {/* Quick actions */}
            {!hasMessages && (
              <div className="mb-2 flex flex-wrap gap-2">
                {quickActions().map((qa) => (
                  <button key={qa.key} type="button" className="rounded-full border px-3 py-1 text-xs hover:bg-accent" onClick={() => setInput(t(qa.prefillKey))}>
                    {t(qa.labelKey)}
                  </button>
                ))}
              </div>
            )}

            <div className="rounded-2xl border border-border bg-card p-2.5 shadow-soft transition-shadow focus-within:shadow-medium sm:p-3">
              <PromptBox
                ref={inputRef}
                value={input}
                onChange={setInput}
                onSend={handleSend}
                onStop={onStopGeneration}
                sending={sending || attaching}
                disabled={attaching}
                placeholder={t('chat.placeholder', 'Ask anything about your career…')}
                onAttachPdf={handleAttach}
                attachment={attachment}
                onRemoveAttachment={() => setAttachment(null)}
                toolbar={modelPicker}
              />
            </div>

            <p className="mt-2 px-1 text-center text-2xs leading-relaxed text-muted-foreground">
              {t('chat.disclaimer', 'AI can make mistakes. Review generated content before using it.')}
            </p>

            {/* Starter prompts — click sends straight away */}
            {!hasMessages && !loading && (
              <div className="chat-suggestions mt-5 divide-y divide-border overflow-hidden rounded-2xl border border-border bg-card/60">
                {STARTER_PROMPTS.map((starter) => (
                  <button
                    key={starter.titleKey}
                    type="button"
                    onClick={() => sendText(t(starter.titleKey))}
                    className="flex w-full flex-col items-start gap-0.5 px-4 py-3 text-left transition-colors hover:bg-accent"
                  >
                    <span className="text-sm font-medium leading-snug text-foreground">{t(starter.titleKey)}</span>
                    <span className="text-xs leading-snug text-muted-foreground">
                      {t(starter.subKey, starter.subFallback)}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Artifact preview — split view on wide screens, full-screen sheet below */}
      {artifact && (
        <ArtifactPanel artifact={artifact} locale={locale} onClose={() => setDismissedArtifactKey(artifactKey)} />
      )}

      {/* Guest limit dialog */}
      <Dialog open={showLoginPrompt} onOpenChange={setShowLoginPrompt} size="sm">
        <DialogHeader>
          <DialogTitle>{t('chat.loginRequired', 'Sign in to continue')}</DialogTitle>
        </DialogHeader>
        <DialogContent>
          <DialogDescription>
            {t('chat.guestLimitReached', {
              limit: GUEST_MESSAGE_LIMIT,
              defaultValue: 'You have used your {limit} free messages. Create a free account to keep chatting and save your conversations.',
            })}
          </DialogDescription>
        </DialogContent>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setShowLoginPrompt(false)}>
            {t('chat.continueAsGuest', 'Maybe later')}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setShowLoginPrompt(false);
              onNewChat?.();
            }}
          >
            {t('chat.startNewChat', 'Start a new chat')}
          </Button>
          <Button
            onClick={() => {
              setShowLoginPrompt(false);
              openAuth('sign-in');
            }}
          >
            {t('auth.signIn')}
          </Button>
        </DialogFooter>
      </Dialog>
    </div>
  );
}
