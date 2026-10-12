import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useGuestMessages, clearGuestMessages } from './useGuestMessages';

// Mock localStorage
const mockLocalStorage = (() => {
  let store = {};
  return {
    getItem: vi.fn((key) => store[key] ?? null),
    setItem: vi.fn((key, value) => {
      store[key] = value.toString();
    }),
    removeItem: vi.fn((key) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage,
});

describe('useGuestMessages', () => {
  beforeEach(() => {
    mockLocalStorage.clear();
    vi.clearAllMocks();
  });

  it('should start with 0 messages when no localStorage value', () => {
    const TestComponent = () => {
      const { count, remaining, hasReachedLimit } = useGuestMessages();
      return (
        <div>
          <span data-testid="count">{count}</span>
          <span data-testid="remaining">{remaining}</span>
          <span data-testid="hasReachedLimit">{String(hasReachedLimit)}</span>
        </div>
      );
    };

    render(<TestComponent />);

    expect(screen.getByTestId('count').textContent).toBe('0');
    expect(screen.getByTestId('remaining').textContent).toBe('5');
    expect(screen.getByTestId('hasReachedLimit').textContent).toBe('false');
  });

  it('should load existing count from localStorage', () => {
    mockLocalStorage.setItem('aca-guest-messages', '3');

    const TestComponent = () => {
      const { count, remaining } = useGuestMessages();
      return (
        <div>
          <span data-testid="count">{count}</span>
          <span data-testid="remaining">{remaining}</span>
        </div>
      );
    };

    render(<TestComponent />);

    expect(screen.getByTestId('count').textContent).toBe('3');
    expect(screen.getByTestId('remaining').textContent).toBe('2');
  });

  it('should increment message count', () => {
    const TestComponent = () => {
      const { count, increment } = useGuestMessages();
      return (
        <div>
          <span data-testid="count">{count}</span>
          <button onClick={increment}>Increment</button>
        </div>
      );
    };

    render(<TestComponent />);

    expect(screen.getByTestId('count').textContent).toBe('0');

    act(() => {
      screen.getByText('Increment').click();
    });

    expect(screen.getByTestId('count').textContent).toBe('1');
  });

  it('should prevent incrementing beyond limit', () => {
    // Set count to 5 (limit)
    mockLocalStorage.setItem('aca-guest-messages', '5');

    const TestComponent = () => {
      const { count, hasReachedLimit, increment } = useGuestMessages();
      return (
        <div>
          <span data-testid="count">{count}</span>
          <span data-testid="hasReachedLimit">{String(hasReachedLimit)}</span>
          <button onClick={increment}>Increment</button>
        </div>
      );
    };

    render(<TestComponent />);

    expect(screen.getByTestId('count').textContent).toBe('5');
    expect(screen.getByTestId('hasReachedLimit').textContent).toBe('true');

    // Try to increment - should return false and not change count
    act(() => {
      screen.getByText('Increment').click();
    });

    expect(screen.getByTestId('count').textContent).toBe('5');
  });

  it('should reset message count', () => {
    mockLocalStorage.setItem('aca-guest-messages', '3');

    const TestComponent = () => {
      const { count, reset } = useGuestMessages();
      return (
        <div>
          <span data-testid="count">{count}</span>
          <button onClick={reset}>Reset</button>
        </div>
      );
    };

    render(<TestComponent />);

    expect(screen.getByTestId('count').textContent).toBe('3');

    act(() => {
      screen.getByText('Reset').click();
    });

    expect(screen.getByTestId('count').textContent).toBe('0');
    expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('aca-guest-messages');
  });

  it('should persist count to localStorage', () => {
    const TestComponent = () => {
      const { increment } = useGuestMessages();
      return <button onClick={increment}>Increment</button>;
    };

    render(<TestComponent />);

    act(() => {
      screen.getByText('Increment').click();
    });

    expect(mockLocalStorage.setItem).toHaveBeenCalledWith('aca-guest-messages', '1');
  });
});

describe('clearGuestMessages', () => {
  beforeEach(() => {
    mockLocalStorage.clear();
    vi.clearAllMocks();
  });

  it('should remove guest messages from localStorage', () => {
    mockLocalStorage.setItem('aca-guest-messages', '3');

    clearGuestMessages();

    expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('aca-guest-messages');
  });
});