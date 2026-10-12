# Claude-style UI redesign — notes

Presentation layer only; API contracts, hooks, i18n, theme system and backend integration are unchanged.

Run: `cd frontend && npm install && npm run dev` (http://localhost:5173) — tests: `npx vitest run`.
(The zip shipped macOS-only node_modules and an out-of-sync lockfile; `package-lock.json` was regenerated.)

Key points
- `src/styles.css`: Claude palette tokens (light/dark), global rules moved into `@layer base` (unlayered CSS was overriding Tailwind utilities), `dark:` follows the `.dark` class, system fonts (no web-font request).
- `components/AppShell.jsx`: shared sidebar/drawer layout for ALL workspaces; owns the single Settings dialog, opened only from the account menu (`UserMenu.jsx`).
- `components/ui/dialog.jsx`: centered card — header (title + X), content, footer; closes on overlay click, X, Escape.
- Fixes found on the way: overlay click never closed dialogs; dialog collapsed to 48px; model picker selection was never sent with the request (now shared store); artifact panel could not be closed; missing i18n keys (en/de/fr); undefined popover/secondary tokens.
- Screenshots: `images/`.
