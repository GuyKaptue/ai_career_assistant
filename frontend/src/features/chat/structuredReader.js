// Pure reader for the `structured` payload returned by POST /api/v1/chat/completions.
// Never throws on missing or unknown keys: older responses and ordinary chat have
// no `structured` at all. The backend stays the single source of truth for intent.

const KNOWN_INTENTS = new Set([
  'match_job', 'tailor_cv', 'cover_letter', 'clarify', 'search_jobs',
]);

export function readStructured(response) {
  const raw = (response && (response.structured ?? response.message?.structured)) || null;
  if (!raw || typeof raw !== 'object') {
    return { kind: 'none', intent: null, raw: null };
  }

  const intent = typeof raw.intent === 'string' ? raw.intent : null;
  const steps = Array.isArray(raw.steps) ? raw.steps.map(readStructuredFromObject) : [];

  let kind = 'none';
  if (intent === 'match_job') kind = 'match';
  else if (intent === 'tailor_cv' || intent === 'cover_letter') kind = 'document';
  else if (intent === 'clarify') kind = 'clarify';
  else if (intent === 'search_jobs') kind = 'search';

  const match = (raw.match && typeof raw.match === 'object') ? raw.match : {};
  const job = (raw.job && typeof raw.job === 'object') ? raw.job : {};
  const document = (raw.document && typeof raw.document === 'object') ? raw.document : {};
  const grounding = (raw.grounding && typeof raw.grounding === 'object') ? raw.grounding : {};
  const input = (raw.input && typeof raw.input === 'object') ? raw.input : {};

  return {
    kind,
    intent,
    raw,
    match: {
      score: typeof match.score === 'number' ? match.score : 0,
      label: typeof match.label === 'string' ? match.label : '',
      matched_skills: Array.isArray(match.matched_skills) ? match.matched_skills : [],
      missing_skills: Array.isArray(match.missing_skills) ? match.missing_skills : [],
      reasons: Array.isArray(match.reasons) ? match.reasons : [],
    },
    job: {
      title: typeof job.title === 'string' ? job.title : '',
      company: typeof job.company === 'string' ? job.company : '',
      source_host: typeof job.source_host === 'string' ? job.source_host : '',
      company_unverified: Boolean(job.company_unverified),
      the_role_fallback: Boolean(job.the_role_fallback),
    },
    document: {
      type: document.type === 'cover_letter' ? 'cover_letter' : (document.type === 'cv' ? 'cv' : ''),
      content: typeof document.content === 'string' ? document.content : '',
      template_id: typeof document.template_id === 'string' ? document.template_id : '',
    },
    grounding: {
      removed: typeof grounding.removed === 'number' ? grounding.removed : 0,
    },
    gaps: Array.isArray(raw.gaps) ? raw.gaps : [],
    missing: Array.isArray(raw.missing) ? raw.missing : [],
    job_ingest_status: typeof raw.job_ingest_status === 'string' ? raw.job_ingest_status : (typeof input.job_ingest_status === 'string' ? input.job_ingest_status : ''),
    steps,
    input: {
      kind: typeof input.kind === 'string' ? input.kind : '',
      job_ingest_status: typeof input.job_ingest_status === 'string' ? input.job_ingest_status : '',
      used_session_job: Boolean(input.used_session_job),
    },
    notes: Array.isArray(raw.notes) ? raw.notes : [],
    questions: Array.isArray(raw.questions) ? raw.questions : [],
    job_matches: Array.isArray(raw.job_matches) ? raw.job_matches : [],
  };
}

function readStructuredFromObject(obj) {
  if (!obj || typeof obj !== 'object') return { kind: 'none', intent: null, raw: obj };
  return readStructured({ structured: obj });
}
