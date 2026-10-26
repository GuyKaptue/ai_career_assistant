import React, { useState } from 'react';
import { useI18n } from '../../i18n';

// Backend job-ingest status -> locale key under chat.ingest.*
const STATUS_MSG = {
  login_wall: 'loginWall',
  not_a_job_posting: 'notAJob',
  fetch_failed: 'fetchFailed',
  invalid_url: 'invalidUrl',
  too_large: 'tooLarge',
  unsupported_type: 'unsupportedType',
  needs_text: 'needsText',
  blocked: 'blocked',
  timeout: 'timeout',
};

export default function ClarifyCard({ data, onUploadCv, onSubmitJob }) {
  const { t } = useI18n();
  const missing = Array.isArray(data?.missing) ? data.missing : [];
  const status = data?.job_ingest_status;
  const [jobText, setJobText] = useState('');
  const [jobUrl, setJobUrl] = useState('');

  if (missing.includes('cv')) {
    return (
      <div className="rounded-2xl border border-border bg-card p-4">
        <p className="text-sm">{t('chat.needCv')}</p>
        <button type="button" className="mt-2 rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground" onClick={() => onUploadCv?.()}>
          {t('chat.uploadCv')}
        </button>
      </div>
    );
  }

  // Unknown failing statuses fall back to the generic "could not fetch" message.
  const statusMsg = status && status !== 'ok' && status !== 'session'
    ? t(`chat.ingest.${STATUS_MSG[status] || 'fetchFailed'}`)
    : null;

  function submit() {
    if (jobText.trim()) onSubmitJob?.({ job_text: jobText });
    else if (jobUrl.trim()) onSubmitJob?.({ job_url: jobUrl.trim() });
  }

  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      {statusMsg && <p className="text-sm" role="status">{statusMsg}</p>}
      <p className="mt-2 text-sm">{t('chat.needJob')}</p>
      <textarea
        className="mt-2 w-full rounded border p-2 text-xs"
        rows={4}
        value={jobText}
        onChange={(e) => setJobText(e.target.value)}
        placeholder={t('chat.jobTextPlaceholder')}
        aria-label={t('chat.jobTextPlaceholder')}
      />
      <input
        className="mt-2 w-full rounded border p-2 text-xs"
        value={jobUrl}
        onChange={(e) => setJobUrl(e.target.value)}
        placeholder={t('chat.jobUrlPlaceholder')}
        aria-label={t('chat.jobUrlPlaceholder')}
      />
      <button type="button" className="mt-2 rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground" onClick={submit}>
        {t('chat.submitJob')}
      </button>
    </div>
  );
}
