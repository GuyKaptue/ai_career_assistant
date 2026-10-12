import { debugLog } from './debug';

/**
 * API base.
 *
 * - Production / staging: set `VITE_API_URL` (e.g. https://api.example.com).
 * - Development: leave it unset. The base then stays *relative*, so requests
 *   go to the dev server's own origin and are proxied to the backend by Vite
 *   (see vite.config.js). This avoids CORS entirely and keeps working when
 *   Vite falls back to a port other than 5173.
 */
const apiBase = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/$/, '')
  : '';

export function getApiBase() {
  return apiBase;
}

export function authHeaders(session, extraHeaders = {}) {
  const headers = { 'Content-Type': 'application/json', ...extraHeaders };
  if (session?.access_token) {
    headers.Authorization = `Bearer ${session.access_token}`;
  }
  return headers;
}

/**
 * Abortable variant of {@link apiRequest}.
 *
 * `signal` lets the caller stop waiting on a long generation. The promise
 * still rejects with the usual shape, so callers treat an abort like any
 * other failure.
 */
export async function apiRequestWithSignal(
  path,
  { method = 'GET', session, body, headers, signal } = {},
) {
  debugLog('api', `${method} ${path}`, { authenticated: Boolean(session?.access_token), hasBody: body !== undefined });
  let response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      method,
      headers: authHeaders(session, headers),
      body: body === undefined ? undefined : JSON.stringify(body),
      ...(signal ? { signal } : {}),
    });
  } catch (error) {
    if (error?.name === 'AbortError') {
      debugLog('api', `ABORTED ${method} ${path}`);
      throw error;
    }
    debugLog('api', `NETWORK FAILED ${method} ${path}`, { message: error?.message || String(error) });
    throw error;
  }

  if (!response.ok) {
    let detail = '';
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || '';
    } catch {
      detail = '';
    }
    debugLog('api', `FAILED ${method} ${path} -> ${response.status}`, { detail: detail.slice(0, 500) });
    throw new Error(detail || `Request failed: ${response.status} ${response.statusText}`);
  }

  debugLog('api', `OK ${method} ${path} -> ${response.status}`);
  return response.json();
}

export async function apiRequest(path, options = {}) {
  return apiRequestWithSignal(path, options);
}

export async function apiUpload(path, { session, formData }) {
  debugLog('api', `UPLOAD ${path}`, { authenticated: Boolean(session?.access_token) });
  const headers = {};
  if (session?.access_token) {
    headers.Authorization = `Bearer ${session.access_token}`;
  }
  let response;
  try {
    response = await fetch(`${apiBase}${path}`, { method: 'POST', headers, body: formData });
  } catch (error) {
    debugLog('api', `UPLOAD NETWORK FAILED ${path}`, {
      message: error?.message || String(error),
      hint: `Backend unreachable at ${apiBase}. Start it and check GET ${apiBase}/health.`,
    });
    throw error;
  }
  if (!response.ok) {
    let detail = '';
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || '';
    } catch {
      detail = '';
    }
    debugLog('api', `UPLOAD FAILED ${path} -> ${response.status}`, { detail: detail.slice(0, 500) });
    throw new Error(detail || `Upload failed: ${response.status} ${response.statusText}`);
  }
  debugLog('api', `UPLOAD OK ${path} -> ${response.status}`);
  return response.json();
}
