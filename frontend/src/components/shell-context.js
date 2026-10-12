import { createContext, useContext } from 'react';

/**
 * Shell state shared by AppShell and its descendants (header toggle, account
 * menu, sidebar content). Kept in its own module so those components can read
 * it without importing AppShell (which would be a circular import).
 */
export const ShellContext = createContext({
  isMobile: false,
  sidebarOpen: true,
  toggleSidebar: () => {},
  closeDrawer: () => {},
});

export function useShell() {
  return useContext(ShellContext);
}
