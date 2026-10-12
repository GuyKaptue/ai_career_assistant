import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

const SettingsDialogContext = createContext({
  openSettings: () => {},
  closeSettings: () => {},
  isOpen: false,
});

/**
 * Owns the single settings dialog instance.
 *
 * The header gear and the sidebar's Settings entry both call `openSettings()`,
 * so the dialog is mounted once and opened from anywhere.
 */
export function SettingsDialogProvider({ children }) {
  const [open, setOpen] = useState(false);

  const openSettings = useCallback(() => setOpen(true), []);
  const closeSettings = useCallback(() => setOpen(false), []);

  const value = useMemo(() => ({ openSettings, closeSettings, isOpen: open }), [openSettings, closeSettings, open]);

  return <SettingsDialogContext.Provider value={value}>{children}</SettingsDialogContext.Provider>;
}

export function useSettingsDialog() {
  return useContext(SettingsDialogContext);
}
