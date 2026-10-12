import React, { createContext, useContext, useEffect, useState } from 'react';

/**
 * Theme Context for AI Career Assistant
 * Supports: Light, Dark, System (auto-detect)
 */

const THEMES = ['light', 'dark', 'system'];
const STORAGE_KEY = 'aca-theme';

/**
 * Context default. Must stay complete: consumers such as ThemeSwitcher read
 * `availableThemes` unconditionally, and an incomplete default throws
 * "Cannot read properties of undefined (reading 'map')" whenever a consumer
 * renders outside a ThemeProvider — including transient HMR states where
 * React can briefly unmount/remount the tree.
 */
const ThemeContext = createContext({
  theme: 'system',
  setTheme: () => {},
  availableThemes: THEMES,
  isLight: true,
  isDark: false,
});

/**
 * Get the user's preferred color scheme from the OS
 */
function getSystemTheme() {
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'light';
}

/**
 * Apply theme to document
 */
function applyTheme(theme) {
  const root = document.documentElement;
  const actualTheme = theme === 'system' ? getSystemTheme() : theme;
  
  root.classList.remove('light', 'dark');
  root.classList.add(actualTheme);
  
  // Also set data-theme attribute for CSS variable access
  root.setAttribute('data-theme', actualTheme);
}

/**
 * Theme Provider Component
 * Persists theme choice in localStorage
 * Applies theme before first paint to prevent flash
 */
export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    if (typeof window === 'undefined') {
      return 'system';
    }
    
    // Check localStorage first
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && THEMES.includes(stored)) {
      return stored;
    }
    
    // Default to system
    return 'system';
  });

  // Apply theme on mount and when theme changes
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Sync with system theme changes. Guarded because `matchMedia` is absent in
  // jsdom and other non-browser environments, and 'system' is the default
  // theme — an unguarded call here throws on mount.
  useEffect(() => {
    if (theme !== 'system' || typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => applyTheme('system');
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme]);

  // Persist theme to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Storage may be unavailable (private mode); ignore.
    }
  }, [theme]);

  const setTheme = (newTheme) => {
    if (THEMES.includes(newTheme)) {
      setThemeState(newTheme);
    }
  };

  const value = {
    theme,
    setTheme,
    availableThemes: THEMES,
    isLight: theme === 'light' || (theme === 'system' && getSystemTheme() === 'light'),
    isDark: theme === 'dark' || (theme === 'system' && getSystemTheme() === 'dark'),
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}

// Initialize theme before React renders to prevent flash
export function initializeTheme() {
  if (typeof document !== 'undefined') {
    const stored = localStorage.getItem(STORAGE_KEY);
    const theme = stored && THEMES.includes(stored) ? stored : 'system';
    applyTheme(theme);
  }
}
