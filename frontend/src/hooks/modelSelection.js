/**
 * Sentinel model id meaning "let the router choose".
 *
 * The backend auto-selects a model per task (chat / CV analysis / cover-letter
 * generation). Selecting this value sends no ``preferred_model_id``, so the
 * router's eliminate-then-rank picks the model; any other value is a manual
 * override that pins the choice for that turn.
 */
export const AUTO_MODEL = 'auto';

/**
 * The model the user picked, shared by every `useModels` consumer.
 *
 * The composer picker, the Settings dialog and the code that builds the chat
 * request all call `useModels`. Each used to own a private `selectedModel`,
 * so choosing a model in one place never reached the request (which always
 * went out as "auto"). The selection now lives in one tiny external store.
 */
let sharedSelection = AUTO_MODEL;
const selectionListeners = new Set();

export function subscribeToSelection(listener) {
  selectionListeners.add(listener);
  return () => selectionListeners.delete(listener);
}

export function readSelection() {
  return sharedSelection;
}

export function writeSelection(next) {
  const value = next || AUTO_MODEL;
  if (value === sharedSelection) return;
  sharedSelection = value;
  selectionListeners.forEach((listener) => listener());
}

/** Back to "auto" — used by tests so one test's pick never leaks into the next. */
export function resetModelSelection() {
  writeSelection(AUTO_MODEL);
}

