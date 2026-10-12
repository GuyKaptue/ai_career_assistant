import React, { useRef, useState } from 'react';

import { apiRequest, apiUpload } from '../../lib/api';
import { debugLog } from '../../lib/debug';
import { useI18n } from '../../i18n';
import { useAsync } from '../../hooks/useAsync';
import { useStatus } from '../../hooks/useStatus';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { Label } from '../../components/ui/label';

/**
 * CV upload button: posts a PDF to POST /api/v1/resume/extract and fills
 * the caller's resume textarea with the extracted text. Used by ATS review
 * (fill resume_text) and job search (fill candidate_text for re-ranking).
 * Only file name/size/type are logged — never file bytes.
 */
export function CvUpload({ session, onExtracted, label }) {
  const { t } = useI18n();
  const { report } = useStatus();
  const inputRef = useRef(null);
  const upload = useAsync();
  const [fileName, setFileName] = useState('');

  async function handleFile(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) {
      return;
    }
    debugLog('cv-upload', 'file selected', { name: file.name, size: file.size, type: file.type });
    setFileName(file.name);
    report(t('cvUpload.uploading'), file.name);
    const formData = new FormData();
    formData.append('file', file, file.name);
    debugLog('cv-upload', 'upload started', { name: file.name, size: file.size });
    const payload = await upload.run(() => apiUpload('/api/v1/resume/extract', { session, formData }));
    if (payload?.text) {
      debugLog('cv-upload', 'upload succeeded', {
        name: file.name,
        chars: payload.chars,
        pages: payload.pages,
      });
      report(t('cvUpload.ready'), t('cvUpload.readySummary', { name: file.name, chars: payload.chars }));
      onExtracted?.(payload.text, payload);
    } else {
      debugLog('cv-upload', 'upload failed', { name: file.name, error: upload.error?.message });
      report(t('cvUpload.failed'), upload.error?.message || t('summary.unableToCheck'));
    }
  }

  return (
    <span className="flex items-center gap-2">
      <Input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        onChange={handleFile}
        className="hidden"
        aria-label={label || t('cvUpload.label')}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => inputRef.current?.click()}
        disabled={upload.phase === 'loading'}
        className="h-8"
      >
        {upload.phase === 'loading' ? t('cvUpload.uploading') : label || t('cvUpload.label')}
      </Button>
      {fileName && upload.phase !== 'loading' && (
        <span className="text-sm text-muted-foreground">{fileName}</span>
      )}
    </span>
  );
}

/**
 * ATS resume review. Owns its resume/job-description inputs and the
 * check action; reports score and matched keywords to the status
 * channel and renders the score inline.
 */
export default function ResumeChecker({ session, onScore }) {
  const { t } = useI18n();
  const { report } = useStatus();
  const [resumeText, setResumeText] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const check = useAsync();

  function handleExtracted(text) {
    debugLog('cv-upload', 'resume text filled from upload', { chars: text.length });
    setResumeText(text);
  }

  async function handleCheckResume() {
    if (!session) {
      report(t('status.signInRequired'), t('summary.signInToCheck'));
      return;
    }

    report(t('status.checkingAts'));
    const payload = await check.run(() =>
      apiRequest('/api/v1/resume/check', {
        method: 'POST',
        session,
        body: { resume_text: resumeText, job_description: jobDescription },
      }),
    );

    if (payload) {
      const score = payload.score ?? 0;
      const keywords = payload.matched_keywords?.join(', ') || t('summary.noKeywords');
      onScore?.(score);
      report(t('status.atsReviewed'), t('summary.atsResult', { score, keywords }));
    } else {
      report(t('status.atsUnavailable'), check.error?.message || t('summary.unableToCheck'));
    }
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>{t('ats.title')}</CardTitle>
        <CardDescription>{t('ats.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <CvUpload session={session} onExtracted={handleExtracted} />
          <Button
            type="button"
            onClick={handleCheckResume}
            disabled={check.phase === 'loading'}
            size="sm"
          >
            {check.phase === 'loading' ? t('ats.checking') : t('ats.check')}
          </Button>
        </div>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="resume-text">{t('ats.resumeText')}</Label>
            <Textarea
              id="resume-text"
              value={resumeText}
              onChange={(event) => setResumeText(event.target.value)}
              placeholder={t('ats.resumeTextPlaceholder')}
              rows={6}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="job-description">{t('ats.jobDescription')}</Label>
            <Textarea
              id="job-description"
              value={jobDescription}
              onChange={(event) => setJobDescription(event.target.value)}
              placeholder={t('ats.jobDescriptionPlaceholder')}
              rows={6}
            />
          </div>
        </div>
        {check.phase === 'error' && (
          <p className="text-sm text-destructive mt-2" role="alert">
            {check.error?.message || t('summary.unableToCheck')}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
