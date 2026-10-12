import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../i18n';
import ChatCanvas, { parseBlocks } from './ChatCanvas';

/**
 * Message renderer contract:
 *   - user turns render as right-aligned bubbles
 *   - assistant turns render markdown-lite blocks (paragraphs, lists, code)
 *   - code fences get a language header and a working Copy button
 *   - Copy / Retry actions sit under assistant messages
 *   - the typing indicator shows while a response is generating
 */
function renderCanvas(props = {}) {
  return render(
    <I18nProvider>
      <ChatCanvas {...props} />
    </I18nProvider>,
  );
}

describe('parseBlocks', () => {
  it('splits fences, bullet lists and paragraphs in order', () => {
    const blocks = parseBlocks('Hello world\n\n- one\n- two\n\n```python\nprint("hi")\n```');

    expect(blocks.map((block) => block.kind)).toEqual(['p', 'list', 'code']);
    expect(blocks[1].items).toEqual(['one', 'two']);
    expect(blocks[2].lang).toBe('python');
    expect(blocks[2].code).toBe('print("hi")');
  });

  it('treats a fence without a language label as unlabeled', () => {
    const [block] = parseBlocks('```\nplain\n```');
    expect(block).toEqual({ kind: 'code', lang: '', code: 'plain' });
  });

  it('returns an empty block list for empty content', () => {
    expect(parseBlocks('')).toEqual([]);
    expect(parseBlocks(null)).toEqual([]);
  });
});

describe('ChatCanvas', () => {
  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('renders a user message as a right-aligned bubble', () => {
    renderCanvas({ messages: [{ id: 'u1', role: 'user', content: 'Hello there' }] });

    expect(screen.getByText('Hello there')).toBeInTheDocument();
  });

  it('renders assistant blocks with bold, inline code and lists', () => {
    renderCanvas({
      messages: [
        {
          id: 'a1',
          role: 'assistant',
          content: 'Use **bold** and `inline_code`.\n- item one',
        },
      ],
    });

    expect(screen.getByText('bold')).toBeInTheDocument();
    expect(screen.getByText('inline_code')).toBeInTheDocument();
    expect(screen.getByText('item one')).toBeInTheDocument();
  });

  it('copies a fenced code block from its header button', async () => {
    renderCanvas({
      messages: [
        {
          id: 'a1',
          role: 'assistant',
          content: '```js\nconsole.log(1);\n```',
        },
      ],
    });

    // The code-block Copy button renders before the message-actions one.
    const [codeCopy] = screen.getAllByRole('button', { name: 'Copy' });
    fireEvent.click(codeCopy);

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('console.log(1);'),
    );
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument();
  });

  it('invokes onRetry from the retry action', () => {
    const onRetry = vi.fn();
    renderCanvas({
      messages: [{ id: 'a1', role: 'assistant', content: 'Answer' }],
      onRetry,
    });

    fireEvent.click(screen.getByRole('button', { name: /Retry/ }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('shows the typing indicator while a response is generating', () => {
    renderCanvas({ messages: [], sending: true });

    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders retrieval citations with a similarity percentage', () => {
    renderCanvas({
      messages: [
        {
          id: 'a1',
          role: 'assistant',
          content: 'See the handbook.',
          citations: [{ source: 'Career Handbook', similarity: 0.83 }],
        },
      ],
    });

    expect(screen.getByText(/Career Handbook/)).toBeInTheDocument();
    expect(screen.getByText(/83%/)).toBeInTheDocument();
  });
});
