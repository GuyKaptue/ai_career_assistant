import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

import AuthDialogs from '../features/auth/AuthDialogs';

const AuthDialogContext = createContext({
  openAuth: () => {},
  closeAuth: () => {},
  isOpen: false,
  mode: 'sign-in',
});

/**
 * Owns exactly one auth dialog for the whole app.
 *
 * Sign-in and sign-up share a single form that toggles internally, so any
 * entry point (header, sidebar, guard) calls `openAuth()` and gets the same
 * instance rather than mounting a competing dialog.
 */
export function AuthDialogProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState('sign-in');

  const openAuth = useCallback((next = 'sign-in') => {
    setMode(next === 'sign-up' ? 'sign-up' : 'sign-in');
    setOpen(true);
  }, []);

  const closeAuth = useCallback(() => setOpen(false), []);

  const value = useMemo(
    () => ({ openAuth, closeAuth, isOpen: open, mode }),
    [openAuth, closeAuth, open, mode],
  );

  return (
    <AuthDialogContext.Provider value={value}>
      {children}
      <AuthDialogs
        open={open}
        mode={mode}
        onOpenChange={setOpen}
        onModeChange={setMode}
      />
    </AuthDialogContext.Provider>
  );
}

export function useAuthDialog() {
  return useContext(AuthDialogContext);
}
