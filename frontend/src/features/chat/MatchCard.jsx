import React from 'react';
import { useI18n } from '../../i18n';

export default function MatchCard({ data, onTailor, onCover }) {
  const { t } = useI18n();
  const m = data?.match || {};
  const job = data?.job || {};
  const score = typeof m.score === 'number' ? Math.max(0, Math.min(100, m.score)) : 0;

  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="flex items-center gap-3">
        <div className="relative h-12 w-12" role="img" aria-label={t('chat.matchScore', { score })}>
          <svg viewBox="0 0 36 36" className="h-12 w-12 -rotate-90" aria-hidden="true">
            <circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" strokeWidth="3" className="text-muted" />
            <circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" strokeWidth="3" className="text-primary" strokeDasharray={`${score} 100`} />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-xs font-semibold" aria-hidden="true">{score}</span>
        </div>
        <div>
          <p className="font-medium">{m.label}</p>
          {job.title && <p className="text-sm text-muted-foreground">{job.title}{job.company ? ` · ${job.company}` : ''}</p>}
          {job.source_host && <p className="text-xs text-muted-foreground">{job.source_host}</p>}
        </div>
      </div>

      {job.company_unverified && <p className="mt-2 text-xs text-muted-foreground">{t('chat.companyUnverified')}</p>}
      {job.the_role_fallback && <p className="mt-2 text-xs text-muted-foreground">{t('chat.roleFallback')}</p>}
      {data?.input?.used_session_job && <p className="mt-2 text-xs text-muted-foreground">{t('chat.usedSessionJob')}</p>}

      {Array.isArray(m.matched_skills) && m.matched_skills.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium">{t('chat.matchedSkills')}</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {m.matched_skills.map((s) => (
              <span key={s} className="rounded-full bg-primary/10 px-2 py-0.5 text-xs">{s}</span>
            ))}
          </div>
        </div>
      )}

      {Array.isArray(m.missing_skills) && m.missing_skills.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium">{t('chat.missingSkills')}</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {m.missing_skills.map((s) => (
              <span key={s} className="rounded-full border border-border bg-muted px-2 py-0.5 text-xs">{s}</span>
            ))}
          </div>
        </div>
      )}

      {Array.isArray(m.reasons) && m.reasons.length > 0 && (
        <ul className="mt-3 list-disc pl-5 text-xs">
          {m.reasons.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className="rounded-lg bg-primary px-3 py-1.5 text-xs text-primary-foreground" onClick={() => onTailor?.()}>{t('chat.tailorCv')}</button>
        <button type="button" className="rounded-lg border px-3 py-1.5 text-xs" onClick={() => onCover?.()}>{t('chat.writeCover')}</button>
      </div>
    </div>
  );
}
