import React, { useState } from 'react';

import { apiRequest } from '../../lib/api';
import { debugLog } from '../../lib/debug';
import { useI18n } from '../../i18n';
import { useAsync } from '../../hooks/useAsync';
import { useStatus } from '../../hooks/useStatus';
import { EmptyState } from '../../components/AsyncStates';
import { CvUpload } from '../resume-checker/ResumeChecker';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Label } from '../../components/ui/label';

const PAGE_SIZE = 5;

/** Only render links the backend marked as safe absolute http(s) URLs. */
function externalUrl(value) {
  if (typeof value !== 'string') {
    return null;
  }
  return /^https?:\/\/[^\s]+$/i.test(value.trim()) ? value.trim() : null;
}

/** Providers whose outcome was not a clean success (partial or failed). */
export function failedProviders(providerStatus) {
  if (!Array.isArray(providerStatus)) {
    return [];
  }
  return providerStatus
    .filter((entry) => entry && entry.status && entry.status !== 'succeeded')
    .map((entry) => entry.provider)
    .filter((name) => typeof name === 'string' && name.length > 0);
}

function postedLabel(value, locale) {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value).trim() || null;
  }
  try {
    return parsed.toLocaleDateString(locale);
  } catch {
    return parsed.toISOString().slice(0, 10);
  }
}

/**
 * Job discovery: search the backend job index (Adzuna, Bundesagentur
 * Jobsuche, Arbeitnow, opt-in Remotive) and optionally save a result
 * into the application tracker.
 *
 * Renders per-result normalized metadata (provider attribution, remote
 * status, salary, posting date) that the provider actually supplied —
 * unknown values stay hidden rather than being invented — plus a
 * partial-failure notice when at least one source was unavailable.
 * Search state is local; saved roles flow through the shared
 * applications store.
 */
export default function JobDiscovery({ session, onCreateApplication }) {
  const { t, locale } = useI18n();
  const { report } = useStatus();
  const [jobQuery, setJobQuery] = useState('data analyst');
  const [jobLocation, setJobLocation] = useState('remote');
  const [candidateText, setCandidateText] = useState('');
  const [candidateName, setCandidateName] = useState('');
  const [jobs, setJobs] = useState([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [degraded, setDegraded] = useState([]);
  const [savingJobId, setSavingJobId] = useState(null);
  const search = useAsync();

  async function runSearch(targetPage) {
    const params = new URLSearchParams({
      query: jobQuery,
      page: String(targetPage),
      limit: String(PAGE_SIZE),
    });
    if (jobLocation.trim()) {
      params.set('location', jobLocation);
    }
    if (candidateText.trim()) {
      params.set('candidate_text', candidateText.trim().slice(0, 20000));
      debugLog('job-search', 'search with CV candidate_text', {
        candidateChars: candidateText.trim().length,
        candidateFile: candidateName || '(pasted/unknown)',
      });
    } else {
      debugLog('job-search', 'search without candidate_text (keyword order only)');
    }

    const payload = await search.run(() => apiRequest(`/api/v1/jobs/search?${params.toString()}`));

    if (!payload) {
      report(t('status.jobSearchUnavailable'), search.error?.message || t('summary.unableToSearch'));
      setJobs([]);
      setDegraded([]);
      setTotal(0);
      setPage(1);
      return;
    }

    setJobs((prev) => (targetPage > 1 ? [...prev, ...(payload.results || [])] : (payload.results || [])));
    setTotal(payload.total || 0);
    setDegraded(failedProviders(payload.provider_status));
    setPage(targetPage);
    report(
      t('status.jobSearchDone'),
      t('summary.jobSearchResult', { count: payload.results?.length || 0, total: payload.total || 0 }),
    );
    debugLog('job-search', 'search ok', {
      query: jobQuery,
      items: payload.results?.length,
      total: payload.total,
    });
  }

  const hasMore = jobs.length > 0 && jobs.length < total;

  async function handleSaveJob(job) {
    if (!session) {
      report(t('status.signInRequired'), t('summary.signInToTrack'));
      return;
    }

    setSavingJobId(job.id);
    try {
      await onCreateApplication?.({
        company: job.company || job.employer || job.organization || '',
        position: job.title || job.name || '',
        status: 'applied',
        external_id: job.id,
        external_url: job.url || '',
      });
      report(t('status.jobSaved'), t('summary.jobSavedToTracker'));
    } catch (error) {
      report(t('status.trackerUnavailable'), error?.message || t('summary.unableToTrack'));
    } finally {
      setSavingJobId(null);
    }
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>{t('jobs.title')}</CardTitle>
        <CardDescription>{t('jobs.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
          <div className="space-y-2">
            <Label htmlFor="job-query">{t('jobs.query')}</Label>
            <Input
              id="job-query"
              value={jobQuery}
              onChange={(event) => setJobQuery(event.target.value)}
              placeholder={t('jobs.queryPlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="job-location">{t('jobs.location')}</Label>
            <Input
              id="job-location"
              value={jobLocation}
              onChange={(event) => setJobLocation(event.target.value)}
              placeholder={t('jobs.locationPlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="job-candidate-file">{t('jobs.candidateFile')}</Label>
            <CvUpload
              session={session}
              onExtracted={(text, info) => {
                setCandidateText(text);
                setCandidateName(info?.name || '');
              }}
              label={candidateName || t('jobs.attachCv')}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="job-candidate-text">{t('jobs.candidateText')}</Label>
          <Textarea
            id="job-candidate-text"
            value={candidateText}
            onChange={(event) => setCandidateText(event.target.value)}
            placeholder={t('jobs.candidateTextPlaceholder')}
            rows={3}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            onClick={() => runSearch(1)}
            disabled={search.phase === 'loading'}
          >
            {search.phase === 'loading' ? t('jobs.searching') : t('jobs.search')}
          </Button>
          {page > 1 && (
            <Button
              variant="outline"
              onClick={() => runSearch(1)}
              disabled={search.phase === 'loading'}
            >
              {t('jobs.firstPage')}
            </Button>
          )}
          {hasMore && (
            <Button
              variant="outline"
              onClick={() => runSearch(page + 1)}
              disabled={search.phase === 'loading'}
            >
              {t('jobs.nextPage')}
            </Button>
          )}
        </div>

        {search.phase === 'error' && (
          <p className="text-sm text-destructive" role="alert">
            {search.error?.message || t('summary.unableToSearch')}
          </p>
        )}

        {degraded.length > 0 && (
          <div
            className="rounded-lg bg-amber-50/70 p-3 text-sm text-amber-700 shadow-sm dark:bg-amber-900/25 dark:text-amber-400"
            role="status"
            aria-live="polite"
          >
            {t('jobs.partialFailure')}: {degraded.join(', ')}
          </div>
        )}

        {jobs.length > 0 && total > 0 && (
          <p className="text-xs text-muted-foreground" aria-live="polite">
            {t('jobs.showing', { count: jobs.length, total })}
          </p>
        )}

        {jobs.length > 0 ? (
          <div className="grid gap-4" role="list">
            {jobs.map((job, index) => {
              const url = externalUrl(job.url);
              const posted = postedLabel(job.posted_at || job.published_at, locale);
              const title = job.title || job.name || t('jobs.untitled');
              return (
                <article
                  key={`${job.id || job.url || index}-${page}`}
                  className="rounded-xl bg-card/80 p-4 shadow-soft"
                  role="listitem"
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold line-clamp-2 break-words">{title}</h3>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {job.company && (
                          <Badge variant="secondary" className="text-xs">
                            {job.company}
                          </Badge>
                        )}
                        {job.location && (
                          <Badge variant="outline" className="text-xs">
                            {job.location}
                          </Badge>
                        )}
                        {job.remote && (
                          <Badge variant="default" className="text-xs">
                            {t('jobs.remote')}
                          </Badge>
                        )}
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground line-clamp-3">
                        {job.description || job.summary || t('jobs.noDescription')}
                      </p>
                      <div className="job-meta mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
                        {job.provider && (
                          <span className="text-xs text-muted-foreground">
                            {t('jobs.via', { provider: job.provider })}
                          </span>
                        )}
                        {job.salary && (
                          <span className="text-xs text-muted-foreground">
                            {t('jobs.salary')}: {job.salary}
                          </span>
                        )}
                        {posted && (
                          <span className="text-xs text-muted-foreground">
                            {t('jobs.posted')}: {posted}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-row gap-2 sm:flex-col">
                      {url && (
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex h-8 items-center justify-center rounded-md bg-background px-3 text-sm font-medium shadow-xs transition-shadow hover:shadow-sm"
                        >
                          {t('jobs.viewRole')}
                        </a>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleSaveJob(job)}
                        disabled={!session || savingJobId === job.id}
                        className="h-8 px-3"
                      >
                        {savingJobId === job.id ? t('jobs.saving') : t('jobs.save')}
                      </Button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : jobs.length === 0 && search.phase !== 'loading' && search.phase !== 'error' ? (
          <EmptyState label={t('jobs.empty')} />
        ) : null}
      </CardContent>
    </Card>
  );
}
