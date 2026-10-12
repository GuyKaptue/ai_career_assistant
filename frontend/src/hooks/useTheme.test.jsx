import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useTheme, ThemeProvider, initializeTheme } from './useTheme';

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

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: query === '(prefers-color-scheme: dark)',
    media: query,
    onchange: null,
    addListener: vi.fn(), // deprecated
    removeListener: vi.fn(), // deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

describe('useTheme', () => {
  beforeEach(() => {
    // Clear mocks before each test
    mockLocalStorage.clear();
    vi.clearAllMocks();
  });

  it('should provide default theme context', () => {
    const TestComponent = () => {
      const { theme, setTheme, availableThemes, isLight, isDark } = useTheme();
      return (
        <div>
          <span data-testid="theme">{theme}</span>
          <span data-testid="availableThemes">{availableThemes.join(',')}</span>
          <span data-testid="isLight">{String(isLight)}</span>
          <span data-testid="isDark">{String(isDark)}</span>
        </div>
      );
    };

    render(
      <ThemeProvider>
        <TestComponent />
      </ThemeProvider>
    );

    expect(screen.getByTestId('theme').textContent).toBe('system');
    expect(screen.getByTestId('availableThemes').textContent).toBe('light,dark,system');
  });

  it('should allow changing themes', () => {
    const TestComponent = () => {
      const { theme, setTheme } = useTheme();
      return (
        <div>
          <span data-testid="theme">{theme}</span>
          <button onClick={() => setTheme('dark')}>Set Dark</button>
          <button onClick={() => setTheme('light')}>Set Light</button>
        </div>
      );
    };

    render(
      <ThemeProvider>
        <TestComponent />
      </ThemeProvider>
    );

    expect(screen.getByTestId('theme').textContent).toBe('system');

    // Change to dark
    act(() => {
      screen.getByText('Set Dark').click();
    });
    expect(screen.getByTestId('theme').textContent).toBe('dark');

    // Change to light
    act(() => {
      screen.getByText('Set Light').click();
    });
    expect(screen.getByTestId('theme').textContent).toBe('light');
  });

  it('should persist theme to localStorage', () => {
    const TestComponent = () => {
      const { setTheme } = useTheme();
      return <button onClick={() => setTheme('dark')}>Set Dark</button>;
    };

    render(
      <ThemeProvider>
        <TestComponent />
      </ThemeProvider>
    );

    act(() => {
      screen.getByText('Set Dark').click();
    });

    expect(mockLocalStorage.setItem).toHaveBeenCalledWith('aca-theme', 'dark');
  });

  it('should load saved theme from localStorage', () => {
    // Set saved theme in localStorage
    mockLocalStorage.setItem('aca-theme', 'dark');

    const TestComponent = () => {
      const { theme } = useTheme();
      return <span data-testid="theme">{theme}</span>;
    };

    render(
      <ThemeProvider>
        <TestComponent />
      </ThemeProvider>
    );

    expect(screen.getByTestId('theme').textContent).toBe('dark');
  });

  it('should ignore invalid themes from localStorage', () => {
    // Set invalid theme in localStorage
    mockLocalStorage.setItem('aca-theme', 'invalid-theme');

    const TestComponent = () => {
      const { theme } = useTheme();
      return <span data-testid="theme">{theme}</span>;
    };

    render(
      <ThemeProvider>
        <TestComponent />
      </ThemeProvider>
    );

    // Should default to 'system' for invalid themes
    expect(screen.getByTestId('theme').textContent).toBe('system');
  });

  it('should calculate isLight and isDark correctly', () => {
    // Mock system theme to light
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: false, // prefers-color-scheme: dark is false, so light
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));

    const TestComponentLight = () => {
      const { isLight, isDark } = useTheme();
      return (
        <div>
          <span data-testid="isLight">{String(isLight)}</span>
          <span data-testid="isDark">{String(isDark)}</span>
        </div>
      );
    };

    // Test with light theme
    render(
      <ThemeProvider>
        <TestComponentLight />
      </ThemeProvider>
    );

    expect(screen.getByTestId('isLight').textContent).toBe('true');
    expect(screen.getByTestId('isDark').textContent).toBe('false');
  });
});

describe('initializeTheme', () => {
  beforeEach(() => {
    mockLocalStorage.clear();
    vi.clearAllMocks();
  });

  it('should apply theme class to document element', () => {
    // Set saved theme
    mockLocalStorage.setItem('aca-theme', 'dark');

    initializeTheme();

    // Check that dark class was added to document element
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('should handle missing localStorage', () => {
    // Clear localStorage
    mockLocalStorage.clear();

    initializeTheme();

    // Should default to system theme, which should apply based on matchMedia
    // Since we're mocking matchMedia to return false for dark, it should apply light
    expect(document.documentElement.classList.contains('light')).toBe(true);
  });
});