/**
 * Shared frontend debug helper (print debugging with a paper trail).
 *
 * `debugLog(scope, message, data)` prints `[ACA:<scope>] <message>` via
 * `console.debug` and appends a timestamped entry to a capped in-memory
 * ring buffer (200 entries). The buffer is exposed as
 * `window.__ACA_DEBUG__` so a broken UI can still be diagnosed by opening
 * devtools and copying the trail. `installGlobalErrorCollector()` wires
 * `window.onerror` / `window.onunhandledrejection` into the same buffer so
 * fatal boot errors (e.g. a future `React is not defined` regression) are
 * captured even when the React tree never mounts. See
 * `docs/debugging/react-not-defined.md` for the incident this was built for.
 *
 * Privacy: never pass tokens, passwords, keys, or file bytes as `data` —
 * log presence/shape (names, sizes, booleans) instead.
 */
const MAX_ENTRIES = 200;

const buffer = [];

function timestamp() {
  return new Date().toISOString();
}

export function debugLog(scope, message, data) {
  const entry = { at: timestamp(), scope, message, data: data ?? null };
  buffer.push(entry);
  if (buffer.length > MAX_ENTRIES) {
    buffer.splice(0, buffer.length - MAX_ENTRIES);
  }
  try {
    if (data === undefined) {
      console.debug(`[ACA:${scope}] ${message}`);
    } else {
      console.debug(`[ACA:${scope}] ${message}`, data);
    }
  } catch {
    // Console may be unavailable; the buffer still holds the trail.
  }
  return entry;
}

export function getDebugBuffer() {
  return buffer.slice();
}

export function installGlobalErrorCollector() {
  if (typeof window === 'undefined' || window.__ACA_DEBUG_INSTALLED__) {
    return;
  }
  window.__ACA_DEBUG_INSTALLED__ = true;
  window.__ACA_DEBUG__ = {
    entries: buffer,
    snapshot: getDebugBuffer,
    hint: 'Copy window.__ACA_DEBUG__.snapshot() with your bug report. See docs/debugging/react-not-defined.md.',
  };
  window.onerror = (message, source, lineno, colno, error) => {
    debugLog('fatal', 'window.onerror', {
      message: String(message),
      source: String(source || ''),
      lineno: Number(lineno) || 0,
      colno: Number(colno) || 0,
      stack: error?.stack ? String(error.stack).slice(0, 2000) : null,
      hint: 'If this is "React is not defined", restart the Vite dev server so frontend/vite.config.js (React plugin) loads, then hard-refresh.',
    });
  };
  window.onunhandledrejection = (event) => {
    const reason = event?.reason;
    debugLog('fatal', 'unhandledrejection', {
      message: reason?.message ? String(reason.message) : String(reason),
      stack: reason?.stack ? String(reason.stack).slice(0, 2000) : null,
    });
  };
}
