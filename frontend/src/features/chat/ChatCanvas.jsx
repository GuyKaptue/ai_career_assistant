import React, { useState } from 'react';
import { useI18n } from '../../i18n';
import { CheckIcon, CopyIcon, RetryIcon } from '../../components/icons';
import { BrandMark } from '../../components/brand/BrandMark';

/**
 * Message renderer.
 *
 * Assistant output is treated as lightweight markdown: fenced code blocks,
 * bullet lists, paragraphs, plus `inline code` and **bold** spans. Everything
 * is rendered as React nodes — never dangerouslySetInnerHTML — so a hostile
 * completion cannot inject markup.
 */

/** Copies text to the clipboard with a hidden-textarea fallback. */
async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the legacy path (e.g. permission denied)
  }
  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}

/** Splits a string into `code` and **bold** spans as React nodes. */
export function renderInline(text, keyPrefix = 'i') {
  const parts = String(text).split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts
    .filter(Boolean)
    .map((part, index) => {
      const key = `${keyPrefix}-${index}`;
      if (part.length > 2 && part.startsWith('`') && part.endsWith('`')) {
        return (
          <code
            key={key}
            className="rounded-md bg-muted px-[0.4em] py-[0.15em] font-mono text-[0.85em] text-foreground"
          >
            {part.slice(1, -1)}
          </code>
        );
      }
      if (part.length > 4 && part.startsWith('**') && part.endsWith('**')) {
        return <strong key={key}>{part.slice(2, -2)}</strong>;
      }
      return <React.Fragment key={key}>{part}</React.Fragment>;
    });
}

/**
 * Splits assistant output into renderable blocks:
 * `{kind:'code'}` fences, `{kind:'list'}` bullet runs, `{kind:'p'}` lines.
 */
export function parseBlocks(content) {
  const blocks = [];
  const segments = String(content || '').split(/```/);
  segments.forEach((segment, index) => {
    if (index % 2 === 1) {
      const newline = segment.indexOf('\n');
      const lang = newline === -1 ? '' : segment.slice(0, newline).trim();
      const code = newline === -1 ? segment : segment.slice(newline + 1);
      blocks.push({ kind: 'code', lang, code: code.replace(/\n$/, '') });
      return;
    }
    let list = null;
    for (const line of segment.split('\n')) {
      const trimmed = line.trim();
      const bullet = trimmed.match(/^[-*]\s+(.*)/);
      if (bullet) {
        if (!list) {
          list = { kind: 'list', items: [] };
          blocks.push(list);
        }
        list.items.push(bullet[1]);
      } else if (trimmed) {
        list = null;
        blocks.push({ kind: 'p', text: trimmed });
      } else {
        list = null;
      }
    }
  });
  return blocks;
}

/** Dark code block with a language label and a Copy button. */
function CodeBlock({ lang, code }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    const ok = await copyText(code);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    }
  }

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-border bg-code-bg text-code-ink">
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-1.5">
        <span className="font-mono text-xs text-code-head">{lang || 'code'}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="rounded-md border border-white/20 px-2 py-0.5 font-mono text-xs text-code-ink transition-colors hover:bg-white/10"
        >
          {copied ? t('chat.copied', 'Copied') : t('chat.copy', 'Copy')}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-xs leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/** Renders the parsed block list of one assistant message. */
function Blocks({ blocks }) {
  return blocks.map((block, index) => {
    if (block.kind === 'code') {
      return <CodeBlock key={index} lang={block.lang} code={block.code} />;
    }
    if (block.kind === 'list') {
      return (
        <ul key={index} className="my-3 flex flex-col gap-1.5 pl-6">
          {block.items.map((item, itemIndex) => (
            <li key={itemIndex} className="list-disc">
              {renderInline(item, `${index}-${itemIndex}`)}
            </li>
          ))}
        </ul>
      );
    }
    return (
      <p key={index} className="my-3 first:mt-0 last:mb-0">
        {renderInline(block.text, String(index))}
      </p>
    );
  });
}

/** Small text button used for the Copy / Retry actions under a message. */
function ActionButton({ onClick, label, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      {children}
      <span>{label}</span>
    </button>
  );
}

/** Copy / Retry row shown under assistant messages. */
function MessageActions({ content, onRetry }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    const ok = await copyText(content);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    }
  }

  return (
    <div className="flex gap-0.5 text-muted-foreground">
      <ActionButton onClick={handleCopy} label={copied ? t('chat.copied', 'Copied') : t('chat.copy', 'Copy')}>
        {copied ? <CheckIcon className="h-3.5 w-3.5" /> : <CopyIcon className="h-3.5 w-3.5" />}
      </ActionButton>
      {onRetry && (
        <ActionButton onClick={onRetry} label={t('chat.retry', 'Retry')}>
          <RetryIcon className="h-3.5 w-3.5" />
        </ActionButton>
      )}
    </div>
  );
}

/**
 * Chat Canvas — displays conversation messages (Claude layout).
 *
 * User turns are rounded bubbles; assistant turns are unboxed serif prose with
 * the brand spark and the Copy / Retry actions underneath.
 */
export default function ChatCanvas({ messages = [], sending = false, onRetry }) {
  const { t } = useI18n();

  return (
    <div className="flex flex-col gap-7">
      {messages.map((message) => {
        if (message.role === 'user') {
          return (
            <div key={message.id} className="flex">
              <div className="max-w-[88%] rounded-2xl bg-user-bubble px-4 py-2.5 text-[15px] leading-relaxed text-foreground sm:max-w-[80%]">
                <p className="whitespace-pre-wrap break-words">{message.content}</p>
              </div>
            </div>
          );
        }

        const blocks = parseBlocks(message.content);
        return (
          <div key={message.id} className="flex min-w-0 flex-col gap-1.5">
            <div className="min-w-0 break-words font-serif text-[16.5px] leading-[1.7] text-foreground">
              <Blocks blocks={blocks} />
            </div>

            {/* Citations from the retrieval layer, when present */}
            {Array.isArray(message.citations) && message.citations.length > 0 && (
              <div className="mt-1 border-t border-border pt-2">
                <div className="mb-1 text-xs font-medium text-muted-foreground">{t('chat.sources')}</div>
                <div className="text-xs text-muted-foreground">
                  {message.citations.map((citation, index) => (
                    <div key={index} className="mb-1">
                      {citation.source || citation.title || t('chat.source')}
                      {typeof citation.similarity === 'number' ? ` (${Math.round(citation.similarity * 100)}%)` : ''}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Review notice on generated career documents */}
            {message.review_before_sending && (
              <p className="text-xs italic text-warning">{t('chat.reviewBeforeSending')}</p>
            )}

            <div className="flex items-center gap-1">
              <BrandMark variant="glyph" size={16} className="mr-1 h-4 w-4 text-primary" aria-hidden="true" />
              <MessageActions content={message.content} onRetry={onRetry} />
            </div>
          </div>
        );
      })}

      {/* Typing indicator while a response is generating */}
      {sending && (
        <div className="flex items-center gap-2" role="status" aria-label={t('chat.thinking')}>
          <BrandMark variant="glyph" size={16} className="h-4 w-4 animate-pulse text-primary" aria-hidden="true" />
          <div className="chat-typing" aria-hidden="true">
            <i />
            <i />
            <i />
          </div>
        </div>
      )}
    </div>
  );
}
