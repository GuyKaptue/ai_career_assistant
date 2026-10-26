// Pure helpers for the chat composer's detection chips. Display-only hints;
// the backend remains the single source of truth for intent.

const URL_RE = /https?:\/\/\S+/i;
const HIRING_WORDS = /\b(hiring|we are looking|we're looking|requirements|responsibilities|qualifications|job description|apply|salary|full.time|part.time)\b/i;

export function detectJobUrl(text) {
  return URL_RE.test(text || '');
}

export function detectJobText(text) {
  const t = (text || '').trim();
  if (t.length < 200) return false;
  const lines = t.split(/\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 3) return false;
  return HIRING_WORDS.test(t);
}

// Labels and prefills are locale keys (chat.*), resolved by the caller with t().
export function quickActions() {
  return [
    { key: 'match', labelKey: 'chat.quickMatch', prefillKey: 'chat.quickMatchPrefill' },
    { key: 'tailor', labelKey: 'chat.quickTailor', prefillKey: 'chat.quickTailorPrefill' },
    { key: 'cover', labelKey: 'chat.quickCover', prefillKey: 'chat.quickCoverPrefill' },
    { key: 'find', labelKey: 'chat.quickFind', prefillKey: 'chat.quickFindPrefill' },
  ];
}
