# Chat UI Audit Report — AI Career Assistant

Date: 2026-10-10 | Scope: frontend chat + backend model/chat routes
Status: **Implemented and verified** — 404 backend tests, 53 frontend tests, clean production build.

## 1. Existing architecture

**Backend (fully implemented, tested):**
- `app/api/routes/chat.py` — `POST /api/v1/chat/sessions`, `GET /api/v1/chat/sessions`, `GET /api/v1/chat/sessions/{id}`, `DELETE /api/v1/chat/sessions/{id}`, `POST /api/v1/chat/completions` (all Bearer-JWT gated)
- `app/application/services/chat_service.py` — RAG-grounded turns (knowledge base + personal documents), deterministic fallback, `preferred_model_id` pinning
- `app/main.py:219` — `GET /api/v1/models` — returns picker-relevant metadata only (no tokens/internals)
- `app/application/services/ai_model_router.py` — `select_model()`, `fallback_chain()`, `generate_with_fallback(preferred_model_id=...)`
- `supabase/migrations/20261011000000_chat.sql` — `chat_sessions` / `chat_messages` with user-scoped RLS (ownership inherited through the parent session)

**Frontend (React 18 + Vite + Tailwind v4, shadcn-style):**
- `App.jsx` → `Chat.jsx` → `ChatLayout.jsx` → `Sidebar`, `ChatHeader`, `ChatBox`
- `frontend/src/hooks/useSession.js` (Supabase auth), `useTheme.jsx`, `useChat.js`, `useModels.js`, `useGuestMessages.jsx`
- `frontend/src/lib/api.js` — `apiRequest`/`apiUpload` with Bearer tokens

## 2. Styling approach

Tailwind v4 (`@import "tailwindcss"`) + CSS custom properties for design tokens in `frontend/src/styles.css`. The chat shell is theme-aware and uses dynamic viewport units (`100dvh`), safe-area insets, and coarse-pointer adjustments so it adapts to phone, tablet, laptop, and desktop.

## 3. Defects found and fixed

| File | Defect | Fix |
|------|--------|-----|
| `ChatHeader.jsx:58` | **Build-breaking syntax error** — unbalanced `)) }` inside the `.map()` | Rewrote the JSX expression block correctly |
| `ChatLayout.jsx:98` | `Button` / `Input` used without imports → `ReferenceError` at render | Added the missing imports |
| `ChatBox.jsx` | Called `setMessages` / `setSending` that did not exist in scope (state was owned by props) | Refactored to consume props from `useChat` (single source of truth); composer keeps only draft/attachment/modal state |
| `JobDiscovery.jsx` | Read `payload.items` / `payload.degraded`, 0-based pagination, `asChild` leaked to the DOM, no partial-status role | Reads `payload.results`, derives degraded providers from `provider_status`, 1-based pagination with incremental append, `role="status"` on the partial notice |
| `JobDiscovery.test.jsx` | `fireEvent.submit` on a button that only has `onClick` | Switched to `fireEvent.click` |
| `Chat.test.jsx` | Mocks returned bare functions for default-exported modules; state leaked across tests | Mocks return `{ default }`, `useChat` is a stateful mock reset via `beforeEach` |
| `en.js` i18n | Duplicate `today` / `yesterday` / `previous7Days` / `older` keys; missing `showing`, `sidebar`, `disclaimer` | Deduplicated and added the missing keys (kept de/fr in parity) |

## 4. Default page change

The **"Generation status / Ready / Select a template and generate a document"** panel (`components/StatusBanner.jsx`) was removed from the default chat page. It is no longer rendered by `ChatLayout.jsx`; the component itself is retained as a reusable `aria-live` status region for the other screens that need it.

## 4b. Borderless elevation (shadow-based surfaces)

Boxed surfaces are now separated by **elevation instead of white borders**. The white/near-white `border` outlines were removed from every panel and replaced with layered shadows that adapt to light and dark themes.

`@theme` gained a full elevation scale (`--shadow-2xs`, `-xs`, `-sm`, `-md`, `-lg`, `-xl`, `-2xl`, plus the design-system aliases `--shadow-soft` → `--shadow-md`, `--shadow-medium` → `--shadow-lg`, `--shadow-strong` → `--shadow-xl`). Dark mode redefines the same tokens with deeper, softer values so panels stay legible on dark surfaces.

| Component | Before | After |
|-----------|--------|-------|
| `ui/card.jsx` | `rounded-xl border bg-card shadow-soft` | `rounded-xl bg-card shadow-soft` |
| `ui/dialog.jsx` | `rounded-xl border bg-card shadow-xl` | `rounded-xl bg-card shadow-2xl` |
| `ui/dropdown-menu.jsx` | `border border-border rounded-lg shadow-medium` | `rounded-lg shadow-lg` |
| `ui/select.jsx` (content) | `border rounded-lg shadow-medium` | `rounded-lg shadow-lg` |
| `JobDiscovery` job card | `border bg-card/80 shadow-soft` | `bg-card/80 shadow-soft` |
| `JobDiscovery` "View role" | `border border-input bg-background` | `bg-background shadow-xs` + `hover:shadow-sm` |
| `JobDiscovery` degraded notice | `border border-amber-200/80` | `shadow-sm` |
| `ApplicationTracker` column | `border bg-card/80` | `bg-card/80 shadow-sm` |
| `ApplicationTracker` card | `border bg-card shadow-soft` | `bg-card shadow-medium` + `hover:shadow-lg` |
| `TemplateGallery` item | `border` / `border-primary` | `shadow-sm` / `shadow-medium` |
| `PromptBox` composer | `border border-border` | `shadow-medium` |
| `ChatHeader` model select | `border border-border` | `shadow-xs` |
| `ArtifactPanel` | `border-l border-border … md:shadow-xl` | `shadow-[-12px_0_32px_…]` |
| `ChatLayout` sidebar | `border-r border-border` | `lg:shadow-sm`, `shadow-2xl` while the drawer is open |

Note: `shadow-soft` and `shadow-medium` were previously **no-op classes** (they were not defined in `@theme`), so several of these surfaces had no shadow at all before this change. They now emit real, layered shadows.

Form-control borders (`Input`, `Textarea`, `Select`, the auth-field input, and the dropdown trigger) use a **recessed inset shadow** (`--shadow-recessed`, aliased to `--shadow-inset`) instead of a border — this keeps the editable-field affordance readable while removing every visible line. The `Button` outline variant and `Badge` outline variant likewise use `shadow-xs` rather than `border-input`.

### Conversation box

The composer (`PromptBox`) is a floating rounded panel: `rounded-xl shadow-medium`, inset from the viewport on larger screens (`mx-2 mb-2 sm:mx-4 sm:mb-4`). Message bubbles are `rounded-2xl` with a squared corner on the speaker's side (`rounded-br-md` / `rounded-bl-md`), user bubbles in `bg-primary shadow-md`, assistant bubbles in `bg-card shadow-medium`. The header, sidebar header, artifact header/footer and the precedent/citation divider all use soft top/bottom shadows instead of `border-t` / `border-b`.

### Welcome message

The welcome state is verified to render correctly in all three locales. `t()` now supports a string fallback as its second argument (previously a string was silently mis-parsed as an interpolation object), so `t('chat.welcomeTitle', 'Welcome to AI Career Assistant')` resolves from the dictionary and falls back safely if a key is ever missing. The welcome block gained an icon tile and the suggested-prompt cards are `rounded-2xl bg-card shadow-soft` with a `hover:shadow-medium` lift.

### Verification of the border sweep

- No `border` / `border-t` / `border-b` / `border-l` / `border-r` declaration remains in any component
- The only remaining `border` occurrences in `styles.css` are **unused token definitions** (`--border`, `--border-strong`, `--card-border`) that no longer render anything
- `.shadow-inset` emits `var(--shadow-recessed)` so the dark-mode override applies (verified: `#18213614` light, `#0000004d` dark)

## 5. Actual Hugging Face models (backend)

- `mistralai/Mistral-7B-Instruct-v0.3`
- `meta-llama/Llama-3.1-8B-Instruct`
- `microsoft/Phi-3-mini-4k-instruct`
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2` (384-dim)

All are open-weight, HF-hosted, routed via the dynamic registry with circuit breakers and fallback chains. `task_profiles.yaml` declares per-task capability requirements (eliminate-then-rank).

## 6. Model loading/selection

Discovery (`ai_discovery.py`) → registry (`ai_registry.py`) → scoring (`ai_scoring.py`) → router (`ai_model_router.py`) → adapter (`shared_router.py`). `GET /api/v1/models` exposes only picker-relevant fields. `preferred_model_id` pins a user selection through the whole chain, and `ChatHeader` reads that endpoint rather than hardcoding model names.

## 7. HF integration limitations

Requires `HF_TOKEN`; gated/unavailable models fall back deterministically (labelled, never fabricated — every assistant turn carries a "review before sending" notice). Community-documented APIs (Arbeitsagentur) are parsed defensively with a fixed `X-API-Key`.

## 8. Preserved behaviour

All career-assistant features, the 404 backend + analytics suites, theme system (light/dark/system persisted to `aca-theme`), i18n (en/de/fr), guest message limits (5, persisted to `aca-guest-messages`), and Supabase auth.

## 9. Responsive / multi-platform design

- **Desktop (≥1024px)** — persistent sticky sidebar (collapsible), header, scrolling transcript, side-by-side artifact panel
- **Tablet / mobile (<1024px)** — slide-in drawer with backdrop, closes on navigation, on Escape, and on breakpoint change; full-width composer
- **Dynamic viewport units** — `100dvh` (with `100vh` fallback) so mobile browser chrome never clips the composer
- **Safe-area insets** — `env(safe-area-inset-bottom)` applied to the composer and sidebar footer for notched devices
- **Coarse pointers** — larger touch targets and `font-size: 1rem` on the textarea to prevent iOS focus zoom
- **Short viewports** — the welcome block collapses below `max-height: 560px` (landscape phones)
- **Reduced motion** — all transitions/animations collapse to ~0ms
- Only the transcript and session list scroll; the page shell never scrolls

## 10. Verification

| Gate | Result |
|------|--------|
| `python -m pytest -q` (backend) | 404 passed, 1 skipped |
| `ruff check` / `ruff format --check` / `mypy` | clean |
| `npm test` (frontend) | 91 passed (16 files) |
| `npm run build` | clean (142 kB gzip JS, 10.2 kB gzip CSS) |
| Visible borders in source | 0 |
| `.shadow-inset` dark override | verified (`#18213614` light, `#0000004d` dark) |
| Suggested-prompt card shadow | `shadow-soft` survives the merge (verified by test) |

Docker verification was not possible locally (no running daemon), consistent with earlier stages.

## 11. Runtime fixes (console + interaction)

| Issue | Cause | Fix |
|-------|-------|-----|
| `value` prop on `select` should not be null | `useModels` returns `selectedModel: null` before `/api/v1/models` resolves (and while the picker is disabled) | `value={selectedModel ?? ''}` and `onChange` maps the empty option back to `null` |
| Welcome description rendered **word-by-word vertically** | The paragraph sat inside a nested `flex flex-col items-center` wrapper with no definite width. A flex item's cross size resolves to `fit-content`, and against an indefinite parent width that degenerates to `min-content` — the longest word — so every word wrapped | The wrapper now has `w-full max-w-2xl mx-auto`, giving a definite width so `max-w-xl` wraps normally. Added `text-balance` / `text-pretty` for even headline and paragraph measure |

## 12. Suggested-prompt cards: shadow silently dropped

The four welcome cards (`chat.suggestedPrompt1…4`) already carried `shadow-soft … hover:shadow-medium`, but the shadow never rendered.

**Root cause — not the markup, the merge.** `Button`'s `outline` variant contributes `shadow-xs hover:shadow-sm`, and the cards then pass `shadow-soft hover:shadow-medium`. `lib/utils.js` used the stock `twMerge`, which only knows Tailwind's built-in shadow scale (`2xs/xs/sm/md/lg/xl`) and has no idea about the custom `@theme` tokens this project defines. It therefore kept **both** classes, and the visual winner was then decided by *stylesheet order*:

```
.shadow-medium{  byte 19814
.shadow-sm{      byte 19988
.shadow-soft{    byte 20228
.shadow-xs{      byte 20400  ← emitted last, so it won
```

`.shadow-xs` overrode `.shadow-soft` even though `shadow-soft` appears later in the class attribute. This affected every component combining a variant shadow with a custom one — a whole class of bug, not just the cards.

**Fix** — `lib/utils.js` now builds its own merge instance with `extendTailwindMerge`, registering `soft`, `medium`, `strong`, `recessed` and `inset` in the `shadow` class group. The last shadow passed now always wins, matching normal Tailwind semantics, and both `shadow-xs` and `hover:shadow-sm` are correctly dropped from the card.

**Regression coverage** — `lib/utils.test.js` (6 cases) pins the behaviour: custom-over-builtin, builtin-over-custom, custom-over-custom, ordinary Tailwind dedupe, falsy values, and the exact class set used by the suggested-prompt cards.

## 13. Sidebar project tiles are actionable

The four project tiles were inert buttons. Each now maps onto a backend session mode and opens a dedicated workspace matching the tile's workflow:

| Tile | Session mode |
|------|--------------|
| Career Coaching | `general` |
| Resume Review | `ats_checker` |
| Interview Prep | `interview_prep` |
| Job Search | `job_search` |

- `ChatLayout.openProject()` calls `chat.createSession({ title, mode })` for signed-in users and falls back to a local `newChat()` for guests, reporting the outcome through the shared status channel.
- Tiles are `aria-pressed` and highlighted when their mode matches the open session.
- Each tile is a rounded `shadow-soft` box that lifts to `shadow-medium` on hover, in a 2-column grid (4 columns while the mobile drawer is open).
- New tests in `features/chat/Sidebar.test.jsx` (9 cases) cover project dispatch, drawer closing, active-mode highlighting, session selection, search filtering, the empty state, and the `groupSessionsByTime` bucketing helper.

## 14. Fluid typography + description shadow box

The welcome description is now a rounded shadow panel, and the whole type
scale has been converted from fixed rem values to a fluid `clamp()` scale so
text is correctly readable and professional on every viewport.

### Description panel

```jsx
<p className="text-description w-full max-w-xl rounded-2xl bg-card/70 px-4 py-3
              text-muted-foreground shadow-soft sm:px-6 sm:py-4">
```

### Fluid type scale (`@theme`)

Every `--text-*` token is `clamp(min, preferred, max)`, so utilities such as
`text-sm` / `text-base` / `text-lg` now scale continuously with the viewport
instead of snapping at breakpoints. Values are rem-based, so the reader's own
browser font-size preference is still honoured.

| Token | 320px | 375px | 768px | 1024px | 1280px | 1920px |
|-------|-------|-------|-------|--------|--------|--------|
| `text-2xs` | 10.0 | 10.0 | 10.5 | 10.8 | 11.0 | 11.0 |
| `text-xs` | 12.0 | 12.0 | 12.6 | 13.0 | 13.0 | 13.0 |
| `text-sm` | 13.0 | 13.1 | 13.8 | 14.2 | 14.7 | 15.0 |
| `text-base` | 14.0 | 14.2 | 14.9 | 15.4 | 15.9 | 16.0 |
| `text-lg` | 15.1 | 15.2 | 16.0 | 16.6 | 17.1 | 18.0 |
| `text-xl` | 16.0 | 16.1 | 17.0 | 17.7 | 18.3 | 19.8 |
| `text-2xl` | 18.0 | 18.0 | 19.4 | 20.3 | 21.2 | 23.6 |
| `text-3xl` | 22.0 | 22.0 | 23.8 | 25.3 | 26.7 | 30.0 |
| `text-4xl` | 24.0 | 24.0 | 26.6 | 28.5 | 30.4 | 35.2 |
| `text-5xl` | 28.0 | 28.0 | 31.6 | 34.5 | 37.3 | 44.3 |

### Shared fluid text classes

- `.text-description` — descriptive copy: `text-sm` → `text-base` → `text-lg`
  across the sm/lg breakpoints, `line-height: 1.7`, `text-wrap: pretty`, and a
  `max-width: 62ch` reading measure.
- `.text-display` — headings: `text-2xl` → `text-3xl` → `text-4xl` → `text-5xl`,
  tight leading, `text-wrap: balance`.

### Other fixed sizes replaced

- `text-[11px]` on the composer disclaimer → `text-2xs`
- `.status-pill` `0.8rem` → `var(--text-xs)`
- `h1` `clamp(1.5rem, 3vw, 2.25rem)` → `var(--text-4xl)`
- `.stat-box strong` `clamp(1.5rem, 2vw, 2.2rem)` → `var(--text-3xl)`
- `body` gains `font-size: var(--text-base)` and `line-height: 1.7`

The one intentionally fixed size left is `font-size: 1rem` on the composer
`textarea` under `@media (pointer: coarse)` — iOS Safari zooms on focus for any
input below 16px, so raising it there is a bug fix, not an oversight.

## 15. Crash fixes + chat-shell integration test

Two genuine crashes, plus the regression test that would have caught them.

### Bug 1 — `ThemeContext` default was incomplete

`ThemeSwitcher` destructures `availableThemes` from `useTheme()` and calls
`availableThemes.map(...)` unconditionally. The context **default value**
only declared `{ theme, setTheme }`, so any consumer rendering outside a
`ThemeProvider` — or during a transient HMR remount — threw
`TypeError: Cannot read properties of undefined (reading 'map')`. The
`ThemeProvider` did supply the value, which is why this only surfaced under
HMR and never in the existing tests.

The default is now complete (`availableThemes`, `isLight`, `isDark`), so a
provider-less consumer degrades instead of crashing.

### Bug 2 — unguarded `matchMedia` in the default theme

`useTheme`'s "sync with system theme changes" effect called
`window.matchMedia(...)` with no guard, and it runs whenever the theme is
`'system'` — **the default**. `getSystemTheme()` guarded for this, the effect
did not. Any environment without `matchMedia` (jsdom, SSR, older browsers)
crashed on mount. The effect is now guarded like the rest of the hook.

### Bug 3 — `select` null value (recurrence check)

`ChatHeader` still passes `value={selectedModel ?? ''}` with the empty option
mapping back to `null`, so the React warning does not recur. Confirmed in the
integration test, which asserts the picker hydrates to a real model id.

### New safety net — `components/ChatLayout.test.jsx`

The existing `Chat.test.jsx` mocks `./Sidebar`, `./ChatCanvas`, `./PromptBox`
and `./ArtifactPanel`, so the real
`Chat -> ChatLayout -> Sidebar / ChatHeader / ChatBox` tree was never
rendered. That is exactly how the reference errors reported from the dev
server (`activeProjectMode is not defined`, `openProject is not defined`,
`activeUser is not defined`) escaped detection: they were wiring mistakes
across several files, and no test rendered the assembled tree.

The new integration test renders the **real** component tree — only Supabase
auth and the REST client are mocked — and covers:

- the whole shell mounts without throwing (no reference errors, no error boundary)
- the welcome heading, description and all four suggested prompts render
- all four real project tiles render and are clickable without crashing
- clicking a suggested prompt fills the composer
- `GET /api/v1/models` hydrates the picker to a real model id

To make that possible, `PromptBox` gained stable `data-testid` hooks
(`prompt-box`, `prompt-input`), matching the names `Chat.test.jsx`'s mock
already used.

### Note on the reported dev-server console noise

The cascading errors in the reported console output (`activeProjectMode`,
`openProject`, `activeUser`, `activeSession` "is not defined") came from Vite
HMR hot-reloading **mid-edit** while the props were being threaded through
`Sidebar` and `ChatLayout` file by file. The `createRoot()` and
`removeChild` errors are React's standard recovery fallout after those
crashes. The on-disk state is consistent (every identifier is declared before
use) and is now covered by the integration test — but a **full page reload**
or dev-server restart is still required to clear the corrupted HMR runtime.

## 16. Frontend/backend connectivity, navigation and the dropdown bug

### The reported "frontend is not connected to the backend"

**Root cause: a CORS port mismatch, not a broken API.** `lib/api.js` defaulted
`apiBase` to the absolute `http://127.0.0.1:8000`, so the browser issued
cross-origin requests to the backend. The backend's `CORS_ORIGINS` allowlist
covered `localhost:5173`, `4173` and `3000` only — but Vite had fallen back to
**port 5174** because 5173 was already in use. `http://localhost:5174` is a
distinct origin for CORS, so every request was blocked before it reached the
route handlers.

Fixed on two independent layers:

- **Vite dev proxy** (`vite.config.js`): `/api`, `/health`, `/ready`, `/docs`
  and `/openapi.json` proxy to the backend. The browser now makes *same-origin*
  requests, so CORS is not involved at all in development.
- **Relative API base** (`lib/api.js`): when `VITE_API_URL` is unset the base
  is `''`, so requests go to the dev server's own origin and through the proxy.
  Production still honours `VITE_API_URL` for an absolute base.
- **CORS defaults** (`backend/app/core/config.py`): `127.0.0.1` is now listed
  alongside `localhost` (the browser sends the origin exactly as typed), plus
  the 5174/5175 fallback ports. Defence-in-depth for the direct path.

Verified: `GET :5174/api/v1/models` → 200, `:5174/health` → 200,
`:5174/api/v1/templates` → 200, and the direct path
`GET 127.0.0.1:8000/api/v1/models` with `Origin: localhost:5174` → 200.

### Every dropdown in the app was inert

`ui/dropdown-menu.jsx` kept a **separate `open` state inside both
`DropdownMenuTrigger` and `DropdownMenuContent`**. The two were disconnected:
clicking the trigger toggled state nothing rendered, while the panel only
opened when the (initially invisible) content itself was clicked — i.e. never.
ThemeSwitcher, UserMenu and the new Settings menu were all dead.

Rewritten with the shared state lifted into `DropdownMenu` and passed down
through context. `DropdownMenuItem` also gained `role="menuitem"` (it had no
role at all), and selecting an item now dismisses the menu.

### Navigation: the chat page was a dead end

`App.jsx` rendered only `<Chat>`. All four other features
(`DocumentStudio`, `ResumeChecker`, `JobDiscovery`, `ApplicationTracker`)
existed but were unreachable, and the sidebar Settings button did nothing.

- `hooks/useView.jsx` — workspace navigation (`chat`, `documents`,
  `resume-checker`, `jobs`, `tracker`), persisted to `localStorage`.
- `App.jsx` routes to the active view.
- `components/SettingsMenu.jsx` — the dropdown that switches workspace,
  exposed from the chat sidebar's Settings button.
- `components/WorkspaceShell.jsx` — header for the non-chat workspaces with a
  **back-to-chat** button, the full workspace menu and the account menu, so
  navigating away from chat is not a one-way trip.
- `pages/{Documents,ResumeChecker,Jobs,Tracker}Page.jsx` own each feature's
  state (via the existing `useTemplates` / `useApplications` hooks).

### One auth form, many entry points

`hooks/useAuthDialog.jsx` owns exactly one `AuthDialogs` instance app-wide. Both
the header and the sidebar call `openAuth(mode)` and get the same dialog, which
toggles between sign-in and sign-up internally. Previously `UserMenu` mounted
its own dialog and the header had two dead buttons.

### Database backing (verified end to end)

| Frontend action | Route | Table / policy |
|---|---|---|
| Open a project tile | `POST /api/v1/chat/sessions` `{title, model_id, mode}` | `chat_sessions` (mode CHECK constraint, user RLS) |
| Send a message | `POST /api/v1/chat/completions` | `chat_messages` (cascades on session delete) |
| Save a job to the tracker | `POST /api/v1/applications` | `applications` |
| Move a Kanban card | `PATCH /api/v1/applications/{id}/status` | `applications` |
| Generate a document | `POST /api/v1/documents/generate` | `documents` |

The four project tiles map to `general`, `ats_checker`, `interview_prep` and
`job_search` — all inside `CHAT_MODES` (the same six values the SQL CHECK
constraint allows), and `ChatStore.create_session` rejects anything else with a
`ValueError` → HTTP 400 before it reaches Postgres. `ChatStore` uses
`SupabaseRepository("chat_sessions", …)` whenever Supabase is configured, so
sessions and messages land in the real database, not the in-memory fallback.

### i18n duplicate keys

`en.js` had **9 duplicated keys in its `chat` block** (`today`, `yesterday`,
`previous7Days`, `older`, `attachCv`, `removeAttachment`, `shiftEnterHint`,
`sources`, `newChat`) and duplicates in `nav` (`documents`, `tracker`, `jobs`).
JavaScript object literals keep the **last** occurrence, so the earlier values
were dead and the effective text was decided by line order — which is why the
nav menu silently rendered "Jobs"/"Application Tracker" instead of the intended
"Job discovery"/"Application tracker". All three locales now have **0 duplicate
keys**; the earlier duplicates were dropped, keeping the last occurrence, so
runtime behaviour is unchanged and only the dead lines are gone.

## 17. UI pass: polished auth + settings dialogs and a richer composer

### Animation was a no-op

`components/ui/dialog.jsx` relied on `animate-in fade-in zoom-in-95 duration-200`,
which come from **tailwindcss-animate — a package this project does not install**.
Every dialog in the app therefore had no open/close motion at all. Rather than
add a dependency, `styles.css` now defines the keyframes (`aca-overlay-in/out`,
`aca-panel-in/out`) with a bottom-sheet variant under 640px and a
`prefers-reduced-motion` override.

### Shared modal base

`components/ui/dialog.jsx` became a real modal, so the auth and settings
dialogs inherit one accessible implementation:

| Concern | Implementation |
|---|---|
| `role="dialog"`, `aria-modal`, labelled by the title | set on the panel |
| focus moved into the panel on open | `[data-autofocus]` else first focusable |
| focus trap | Tab/Shift+Tab cycle inside the panel |
| Escape to close | captured listener, stopped from double-handling |
| focus restored to the opener | on unmount, guarded with `document.contains` |
| background scroll locked | `body.overflow` saved and restored |
| exit animation | panel stays mounted 150ms, `closing` state drives the out class |
| scrollable body | `max-h-[92dvh]`, inner `overflow-y-auto` |

### Auth dialog — one dialog, two tabs

Previously the header had two separate buttons and `UserMenu` mounted its own
`AuthDialogs`, so more than one dialog could exist. `AuthDialogProvider`
already fixed that; the dialog is now a proper ARIA tab pair (`role="tablist"`,
`aria-selected`, `aria-controls`, arrow-key switch) rather than two stacked
forms. Added per-field labels, inline validation wired with
`aria-invalid`/`aria-describedby` and `role="alert"` for the message, a
document-level error alert, a spinner on the submit button with every field
disabled while pending, and a reset-on-close so no credentials linger.

### Settings is now a dialog

`components/SettingsDialog.jsx` replaces the workspace dropdown, using the same
design language (sidebar-within-dialog so the sections stay usable on a phone):

- **Workspaces** — navigates to the pages not shown on the chat screen
- **Appearance** — a real `role="radiogroup"` for light/dark/system, applied live
- **AI Models** — the picker, defaulting to **Auto**, showing the model auto-selection
  resolved and labelling unavailable models instead of hiding them
- **Account** — the signed-in user with sign-out, or the auth entry points

`SettingsMenu` is now just the button that opens it; `WorkspaceShell` renders
the same dialog so users can navigate back from the non-chat pages.

### Composer

`features/chat/PromptBox.jsx`:

- auto-grow to a 200px ceiling, then scroll
- live `{chars}/{max} characters · ~{tokens} tokens` counter that turns amber
  near the limit and blocks sending past it
- Enter sends, Shift+Enter inserts a newline, and Enter is ignored while an IME
  composition is active (it would otherwise commit mid-composition)
- while generating, the send button becomes a **Stop** button backed by a new
  `AbortController` in `useChat` and an abortable `apiRequestWithSignal` in
  `lib/api.js`; the optimistic prompt is kept, the spinner dropped

Abort cancels the client wait; the backend turn may still finish, which is
labelled honestly rather than claimed as stopped server-side.

## 18. Tests

| File | Tests |
|---|---|
| `components/ui/dialog.test.jsx` | 7 — modal surface, focus in/out, Escape, overlay, Tab trap, scroll lock |
| `features/auth/AuthDialogs.test.jsx` | 12 — tabs, arrow keys, validation, loading/disabled, payload, field reset |
| `components/SettingsDialog.test.jsx` | 10 — all four sections, navigation, theme radiogroup, model picker, account |
| `features/chat/PromptBox.test.jsx` | 13 — auto-grow, counter, Enter/Shift+Enter, IME safety, stop button, PDF rules |

**Frontend total: 135 passed (20 files).**

## 19. Files changed

```
frontend/src/vite.config.js                          /api dev proxy to the backend
frontend/src/lib/api.js                              relative API base by default
backend/app/core/config.py                           127.0.0.1 + fallback dev ports in CORS defaults
frontend/src/components/ui/dropdown-menu.jsx        shared open state via context (was inert)
frontend/src/hooks/useView.jsx                      workspace navigation, persisted
frontend/src/hooks/useAuthDialog.jsx                one shared auth dialog for the app
frontend/src/components/SettingsMenu.jsx            workspace navigation dropdown
frontend/src/components/WorkspaceShell.jsx          back-to-chat shell for non-chat workspaces
frontend/src/components/UserMenu.jsx                single sign-in entry, shared dialog
frontend/src/features/chat/ChatHeader.jsx           single sign-in entry, shared dialog
frontend/src/features/chat/Sidebar.jsx              Settings wired to SettingsMenu
frontend/src/App.jsx                                 routes to the active workspace
frontend/src/main.jsx                                ViewProvider + AuthDialogProvider
frontend/src/pages/{Documents,ResumeChecker,Jobs,Tracker}Page.jsx  workspace pages
frontend/src/components/ui/dialog.jsx                accessible modal base (focus trap, Esc, animation)
frontend/src/components/SettingsDialog.jsx           new — settings dialog with 4 sections
frontend/src/hooks/useSettingsDialog.jsx             new — owns the single settings dialog
frontend/src/features/auth/AuthDialogs.jsx           tabbed form, validation, loading state
frontend/src/features/chat/PromptBox.jsx             counter, IME-safe keys, stop button
frontend/src/hooks/useAuthDialog.jsx                 complete context default + guarded matchMedia effect
frontend/src/hooks/useChat.js                        stopGeneration + AbortController
frontend/src/hooks/useTheme.jsx                      complete context default + guarded matchMedia effect
frontend/src/lib/api.js                              abortable apiRequestWithSignal
frontend/src/components/ChatLayout.jsx               settings dialog + stop wiring
frontend/src/components/WorkspaceShell.jsx           settings dialog
frontend/src/components/SettingsMenu.jsx             opens the settings dialog
frontend/src/features/chat/ChatHeader.jsx            settings entry + model picker
frontend/src/features/chat/ChatBox.jsx               stop-generation wiring
frontend/src/main.jsx                                 SettingsDialogProvider
frontend/src/i18n/locales/{en,de,fr}.js               auth/settings/composer keys
frontend/src/styles.css                               modal animation keyframes
frontend/src/components/ui/dialog.test.jsx           new — 7 tests
frontend/src/features/auth/AuthDialogs.test.jsx      new — 12 tests
frontend/src/components/SettingsDialog.test.jsx      new — 10 tests
frontend/src/features/chat/PromptBox.test.jsx        new — 13 tests
frontend/src/App.test.jsx                            settings-dialog integration coverage
frontend/src/i18n/locales/{en,de,fr}.js               nav/auth keys + duplicate-key cleanup
frontend/src/styles.css                           fluid clamp() type scale + .text-description/.text-display
frontend/src/features/chat/ChatBox.jsx            description shadow panel + text-2xs disclaimer
frontend/src/lib/utils.js                        extendTailwindMerge with custom shadow scale
frontend/src/lib/utils.test.js                   new — 6 regression tests for cn()
frontend/src/features/chat/ChatHeader.jsx        select value ?? '' fix
frontend/src/features/chat/Sidebar.jsx           actionable project tiles with shadow
frontend/src/features/chat/Sidebar.test.jsx      new — 9 tests (projects, sessions, bucketing)
frontend/src/components/ChatLayout.jsx           openProject() wiring + useStatus
frontend/src/hooks/useChat.js                   createSession() with mode
frontend/src/i18n/locales/{en,de,fr}.js           openProject / projectOpened keys
```
