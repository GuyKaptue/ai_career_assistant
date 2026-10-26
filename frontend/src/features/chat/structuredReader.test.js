import { describe, expect, it } from 'vitest';

import { readStructured } from './structuredReader';

describe('readStructured', () => {
  it('returns kind none when there is no structured field', () => {
    expect(readStructured({ message: { content: 'hi' } }).kind).toBe('none');
    expect(readStructured(null).kind).toBe('none');
    expect(readStructured({}).kind).toBe('none');
  });

  it('never throws on unknown keys', () => {
    const out = readStructured({ structured: { intent: 'match_job', foo: { bar: 1 }, match: { score: 42, weird: true } } });
    expect(out.kind).toBe('match');
    expect(out.match.score).toBe(42);
  });

  it('reads a match turn', () => {
    const out = readStructured({
      structured: {
        intent: 'match_job',
        match: { score: 73, label: 'Strong', matched_skills: ['Python'], missing_skills: ['Kafka'], reasons: ['r'] },
        job: { title: 'Data Engineer', company: 'Acme', source_host: 'jobs.example', company_unverified: true, the_role_fallback: false },
        input: { kind: 'job_url', job_ingest_status: 'ok', used_session_job: false },
      },
    });
    expect(out.kind).toBe('match');
    expect(out.match.score).toBe(73);
    expect(out.job.company_unverified).toBe(true);
    expect(out.input.used_session_job).toBe(false);
  });

  it('reads a document turn', () => {
    const out = readStructured({
      structured: {
        intent: 'tailor_cv',
        document: { type: 'cv', content: 'hello', template_id: 'modern' },
        grounding: { removed: 2 },
        gaps: ['gap1'],
      },
    });
    expect(out.kind).toBe('document');
    expect(out.document.type).toBe('cv');
    expect(out.grounding.removed).toBe(2);
    expect(out.gaps).toEqual(['gap1']);
  });

  it('reads a cover_letter document', () => {
    const out = readStructured({ structured: { intent: 'cover_letter', document: { type: 'cover_letter', content: 'x', template_id: 'classic-letter' } } });
    expect(out.kind).toBe('document');
    expect(out.document.type).toBe('cover_letter');
  });

  it('reads clarify with missing and ingest status', () => {
    const out = readStructured({ structured: { intent: 'clarify', missing: ['cv', 'job'], job_ingest_status: 'login_wall', input: { kind: 'job_url', job_ingest_status: 'login_wall', used_session_job: false } } });
    expect(out.kind).toBe('clarify');
    expect(out.missing).toEqual(['cv', 'job']);
    expect(out.job_ingest_status).toBe('login_wall');
  });

  it('reads every job_ingest_status without throwing', () => {
    for (const st of ['ok', 'login_wall', 'not_a_job_posting', 'fetch_failed', 'invalid_url', 'too_large', 'unsupported_type', 'session']) {
      const out = readStructured({ structured: { intent: 'clarify', job_ingest_status: st } });
      expect(out.job_ingest_status).toBe(st);
    }
  });

  it('reads two-step turns', () => {
    const out = readStructured({
      structured: {
        intent: 'match_job',
        match: { score: 50, label: 'x', matched_skills: [], missing_skills: [], reasons: [] },
        job: { title: 'J', company: '', source_host: '', company_unverified: false, the_role_fallback: false },
        document: { type: 'cover_letter', content: 'doc', template_id: 't' },
        grounding: { removed: 0 },
        gaps: [],
        steps: [
          { intent: 'match_job', match: { score: 50, label: 'x', matched_skills: [], missing_skills: [], reasons: [] }, job: { title: 'J', company: '', source_host: '', company_unverified: false, the_role_fallback: false } },
          { intent: 'cover_letter', document: { type: 'cover_letter', content: 'doc', template_id: 't' }, grounding: { removed: 0 }, gaps: [] },
        ],
      },
    });
    expect(out.steps).toHaveLength(2);
    expect(out.steps[0].kind).toBe('match');
    expect(out.steps[1].kind).toBe('document');
  });

  it('reads search_jobs keeping job_matches', () => {
    const out = readStructured({ structured: { intent: 'search_jobs', job_matches: [{ match_score: 0.5, matched_skills: ['a'] }] } });
    expect(out.kind).toBe('search');
    expect(out.job_matches).toHaveLength(1);
  });

  it('handles ordinary chat with no structured', () => {
    const out = readStructured({ intent: 'general' });
    expect(out.kind).toBe('none');
  });
});
