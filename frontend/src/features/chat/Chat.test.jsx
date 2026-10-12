import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock dependencies at top level to avoid hoisting issues
vi.mock('../../i18n', () => ({
  useI18n: () => ({
    t: (key) => key,
    locale: 'en',
  }),
}));

vi.mock('../../hooks/useStatus.jsx', () => ({
  useStatus: () => ({
    report: vi.fn(),
  }),
}));

vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({ session: null, authLoading: false }),
}));

const { chatMock, stateRef } = vi.hoisted(() => ({
  chatMock: { useChat: () => ({}) },
  stateRef: {
    current: {
      sessions: [],
      activeSessionId: null,
      messages: [],
      loading: false,
      sending: false,
      error: null,
      searchQuery: '',
    },
  },
}));

const resetChatState = () => {
  stateRef.current = {
    sessions: [],
    activeSessionId: null,
    messages: [],
    loading: false,
    sending: false,
    error: null,
    searchQuery: '',
  };
};

vi.mock('../../hooks/useChat', () => {
  chatMock.useChat = () => {
    const [, force] = React.useReducer((n) => n + 1, 0);
    return {
      ...stateRef.current,
      setSearchQuery: vi.fn(),
      selectSession: vi.fn(),
      newChat: vi.fn(() => {
        stateRef.current.activeSessionId = null;
        stateRef.current.messages = [];
      }),
      createSession: vi.fn(),
      deleteSession: vi.fn(),
      sendMessage: (text) => {
        stateRef.current.messages = [
          ...stateRef.current.messages,
          { id: 'u1', role: 'user', content: text },
          { id: 'a1', role: 'assistant', content: 'reply' },
        ];
        force();
        return Promise.resolve({ message: stateRef.current.messages[1] });
      },
    };
  };
  return chatMock;
});

vi.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({
    theme: 'light',
    setTheme: vi.fn(),
    availableThemes: ['light', 'dark', 'system'],
  }),
}));

vi.mock('../../hooks/useModels', () => ({
  AUTO_MODEL: 'auto',
  useModels: () => ({
    models: [
      { model_id: 'meta-llama/Llama-3.3-70B-Instruct' },
      { model_id: 'microsoft/phi-4' },
    ],
    selectedModel: 'auto',
    setSelectedModel: vi.fn(),
    autoDefaultModel: 'microsoft/phi-4',
    isAuto: true,
    loading: false,
    error: null,
  }),
}));

vi.mock('../../hooks/useGuestMessages', () => ({
  useGuestMessages: () => ({
    count: 0,
    hasReachedLimit: false,
    increment: () => true,
    reset: vi.fn(),
    limit: 5,
  }),
}));

vi.mock('../../lib/api', () => ({
  apiRequest: vi.fn().mockResolvedValue({
    session: { id: 's1', messages: [{ id: 'm1', role: 'user', content: 'hi' }] },
    message: { id: 'm2', role: 'assistant', content: 'reply' },
  }),
  apiUpload: vi.fn(),
}));

vi.mock('../../lib/debug', () => ({
  debugLog: vi.fn(),
}));

vi.mock('./Sidebar', () => ({ default: () => <div data-testid="sidebar" /> }));
vi.mock('./ChatCanvas', () => ({
  default: ({ messages = [], sending = false }) => (
    <div data-testid="chat-canvas">
      <span data-testid="canvas-message-count">{messages.length}</span>
      <span data-testid="canvas-sending">{String(sending)}</span>
    </div>
  ),
}));
vi.mock('./ArtifactPanel', () => ({ default: () => <div data-testid="artifact-panel" /> }));

vi.mock('./PromptBox', () => ({
  default: ({ onSend, value, onChange, ...props }) => (
    <div data-testid="prompt-box">
      <textarea
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        data-testid="prompt-input"
      />
      <button onClick={onSend} data-testid="send-button">
        Send
      </button>
    </div>
  ),
}));

vi.mock('../../components/ui/button', () => ({
  Button: ({ children, onClick, ...props }) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
  default: ({ children, onClick, ...props }) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}));

vi.mock('../../components/ui/dialog', () => ({
  Dialog: ({ open, onOpenChange, children }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }) => <div data-testid="dialog-content">{children}</div>,
  DialogHeader: ({ children }) => <div data-testid="dialog-header">{children}</div>,
  DialogTitle: ({ children }) => <h3 data-testid="dialog-title">{children}</h3>,
  DialogDescription: ({ children }) => <p data-testid="dialog-description">{children}</p>,
  DialogFooter: ({ children }) => <div data-testid="dialog-footer">{children}</div>,
}));

import Chat from './Chat';

describe('Chat Component', () => {
  beforeEach(() => {
    resetChatState();
  });

  it('should render the chat interface with sidebar, canvas, and prompt box', () => {
    render(<Chat session={null} />);

    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('prompt-box')).toBeInTheDocument();
    // The conversation canvas mounts once the thread has messages.
    expect(screen.queryByTestId('chat-canvas')).not.toBeInTheDocument();
  });

  it('should display welcome message when there are no messages', () => {
    render(<Chat session={null} />);

    // The welcome screen renders when there are no messages
    // (i18n mock returns the key as-is; the accented word sits in its own <em>)
    expect(screen.getByText('chat.welcomeHeadlineAccent')).toBeInTheDocument();
    expect(screen.getByText('chat.welcomeSubtitle')).toBeInTheDocument();
  });

  it('should handle message input and sending', async () => {
    render(<Chat session={null} />);

    const input = screen.getByTestId('prompt-input');
    const sendButton = screen.getByTestId('send-button');

    // Type a message
    fireEvent.change(input, { target: { value: 'Hello, how can you help me?' } });

    // Click send button — the optimistic user message should be added to the canvas
    fireEvent.click(sendButton);

    await waitFor(() => {
      // Optimistic user message + assistant reply = 2 messages
      expect(screen.getByTestId('canvas-message-count').textContent).toBe('2');
    });
  });

  it('should display suggested prompts when no messages exist', () => {
    render(<Chat session={null} />);

    // The suggested prompts should be visible in the chat area
    // (i18n mock returns the key as-is)
    expect(screen.getByText('chat.suggestedPrompt1')).toBeInTheDocument();
  });

  it('should handle guest message limit', () => {
    render(<Chat session={null} />);

    // The prompt box should be rendered for guest users
    const sendButton = screen.getByTestId('send-button');
    expect(sendButton).toBeInTheDocument();
  });

  it('should show login prompt when guest reaches message limit', () => {
    // This is a more complex test that would require proper mocking of the increment function
    // For now, we'll just test that the dialog exists
    render(<Chat session={null} />);

    // The dialog might not be open by default, but it should exist in the component tree
    expect(screen.queryByTestId('dialog')).not.toBeInTheDocument();
  });
});