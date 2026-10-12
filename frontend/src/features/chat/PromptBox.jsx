import React, { useEffect, useImperativeHandle, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import { Button } from '../../components/ui/button';
import { ArrowUpIcon, PaperclipIcon, XIcon } from '../../components/icons';
// (PaperclipIcon / XIcon keep the attachment chip on the shared stroke-icon
//  set instead of emoji, so the whole composer is visually consistent.)

const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024; // 5 MB
/** Hard ceiling on the prompt length; the counter turns amber near it. */
const MAX_CHARS = 8000;
/** ~4 characters per token — deliberately an estimate, labelled as such. */
const CHARS_PER_TOKEN = 4;
/** Tallest the textarea may grow before it starts scrolling. */
const MAX_TEXTAREA_HEIGHT = 200;

/**
 * Chat composer.
 *
 * - multi-line textarea that grows with the content up to a ceiling
 * - live character / estimated-token indicator against the prompt budget
 * - Enter sends, Shift+Enter inserts a newline (IME composition safe)
 * - while a response is being generated the send button becomes a Stop
 *   button that cancels the in-flight request
 */
const PromptBoxComponent = (
  {
    value,
    onChange,
    onSend,
    onStop,
    sending = false,
    disabled = false,
    onAttachPdf,
    attachment = null,
    onRemoveAttachment,
    placeholder = 'Ask anything...',
    toolbar = null,
  },
  ref
) => {
  const { t } = useI18n();
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const [attachmentError, setAttachmentError] = useState('');
  const [composing, setComposing] = useState(false);

  // Expose the textarea so parents can focus it (e.g. Cmd/Ctrl+K).
  useImperativeHandle(ref, () => textareaRef.current);

  // Auto-grow: reset the height, then let the content decide it.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [value]);

  const trimmed = value.trim();
  const length = value.length;
  const near = length > MAX_CHARS * 0.9;
  const over = length > MAX_CHARS;
  const estimatedTokens = Math.ceil(length / CHARS_PER_TOKEN);
  const canSend = !sending && !disabled && !over && (trimmed.length > 0 || attachment !== null);

  function handleKeyDown(event) {
    // Enter sends, but never while an IME composition is active.
    if (event.key === 'Enter' && !event.shiftKey && !composing) {
      event.preventDefault();
      if (canSend) onSend?.();
    }
  }

  function handleFile(event) {
    const file = event.target.files?.[0];
    event.target.value = ''; // allow re-selecting the same file
    if (!file) return;

    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setAttachmentError(t('chat.attachPdfOnly'));
      return;
    }
    if (file.size > MAX_ATTACHMENT_BYTES) {
      setAttachmentError(t('chat.fileTooLarge'));
      return;
    }
    setAttachmentError('');
    onAttachPdf?.(file);
  }

  function handleStop() {
    onStop?.();
  }

  return (
    <div className="@container flex flex-col gap-1.5" data-testid="prompt-box">
      {/* Attachment chip */}
      {attachment && (
        <div className="flex items-center gap-2 rounded-xl bg-muted px-3 py-2">
          <PaperclipIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate text-sm" title={attachment.name}>
            {attachment.name}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setAttachmentError('');
              onRemoveAttachment?.();
            }}
            className="h-6 w-6 rounded-full p-0"
            aria-label={t('chat.removeAttachment')}
          >
            <XIcon className="h-4 w-4" />
          </Button>
        </div>
      )}

      {attachmentError && (
        <p role="alert" className="px-1 text-xs text-destructive">
          {attachmentError}
        </p>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={handleFile}
        data-testid="prompt-file-input"
      />

      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        onKeyDown={handleKeyDown}
        onCompositionStart={() => setComposing(true)}
        onCompositionEnd={() => setComposing(false)}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        className="max-h-[200px] min-h-[44px] w-full resize-none border-none bg-transparent px-2 py-2 text-base leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none sm:text-[15px]"
        aria-label={placeholder}
        data-testid="prompt-input"
      />

      {/* Tool row: attach on the left; counter, model picker and send on the right */}
      <div className="flex items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className="h-8 w-8 shrink-0 rounded-lg text-muted-foreground"
          aria-label={t('chat.attachCv')}
          title={t('chat.attachCv')}
        >
          <PaperclipIcon className="h-[18px] w-[18px]" />
        </Button>

        <p className="ml-1 hidden min-w-0 truncate text-2xs text-muted-foreground @2xl:block">{t('chat.shiftEnterHint')}</p>

        <div className="ml-auto flex min-w-0 shrink items-center gap-1">
          <p
            className={`hidden shrink-0 text-2xs tabular-nums @md:block ${
              over ? 'font-medium text-destructive' : near ? 'text-warning' : 'text-muted-foreground'
            }`}
            role={over ? 'alert' : undefined}
            aria-live="polite"
            data-testid="prompt-counter"
          >
            {t('chat.promptCounter', {
              chars: length.toLocaleString(),
              max: MAX_CHARS.toLocaleString(),
              tokens: estimatedTokens.toLocaleString(),
            })}
          </p>

          {toolbar}

          {sending ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleStop}
              className="h-8 shrink-0 gap-2 rounded-lg px-3"
              aria-label={t('chat.stop')}
              title={t('chat.stop')}
              data-testid="stop-button"
            >
              <span className="h-2.5 w-2.5 rounded-sm bg-current" aria-hidden="true" />
              <span className="hidden text-xs sm:inline">{t('chat.stop')}</span>
            </Button>
          ) : (
            <Button
              type="button"
              size="icon"
              onClick={() => canSend && onSend?.()}
              disabled={!canSend}
              className="h-8 w-8 shrink-0 rounded-lg disabled:opacity-40"
              aria-label={t('chat.send')}
              title={t('chat.send')}
              data-testid="send-button"
            >
              <ArrowUpIcon className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default React.forwardRef(PromptBoxComponent);
