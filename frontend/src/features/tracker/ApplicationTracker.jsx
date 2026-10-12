import React, { useState } from 'react';

import { useI18n } from '../../i18n';
import { useStatus } from '../../hooks/useStatus';
import { EmptyState, LoadingState } from '../../components/AsyncStates';
import AuthGuard from '../../components/AuthGuard';
import { XIcon } from '../../components/icons';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { Label } from '../../components/ui/label';

const PIPELINE_STAGES = ['applied', 'interview', 'offer', 'rejected'];

/**
 * Kanban board over the user's applications. Cards move between
 * stages with PATCH /applications/{id}/status and are removed with
 * DELETE /applications/{id}. Buttons (not drag-and-drop) keep every
 * action keyboard- and screen-reader-accessible.
 */
function KanbanBoard({ applications, onMove, onDelete, t }) {
  return (
    <div
      className="grid gap-3 @sm:grid-cols-2 @3xl:grid-cols-4"
      role="list"
      aria-label={t('kanban.board')}
    >
      {PIPELINE_STAGES.map((stage, index) => {
        const cards = applications.filter(
          (application) => (application.status || 'applied') === stage,
        );
        return (
          <div
            key={stage}
            className="flex flex-col gap-2 rounded-xl bg-card/80 p-4 shadow-sm"
          >
            <div className="flex items-center justify-between gap-2 mb-2">
              <h3 className="truncate text-xs font-semibold uppercase tracking-wide">
                {t(`kanban.${stage}`)}
              </h3>
              <span
                className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-xs font-bold"
                aria-label={`${cards.length}`}
              >
                {cards.length}
              </span>
            </div>
            {cards.length === 0 ? (
              <p className="text-center text-xs text-muted-foreground py-2">
                {t('kanban.empty')}
              </p>
            ) : (
              cards.map((application) => (
                <article
                  key={application.id}
                  className="flex flex-col gap-2 rounded-lg bg-card p-3 text-sm shadow-medium transition-shadow hover:shadow-lg"
                  role="listitem"
                  aria-label={`${application.position || application.role} — ${application.company}`}
                >
                  <div>
                    <strong className="block font-medium">
                      {application.position || application.role}
                    </strong>
                    <p className="text-xs text-muted-foreground">
                      {application.company}
                    </p>
                  </div>
                  <div className="flex gap-1 justify-end">
                    {index > 0 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => onMove(application, PIPELINE_STAGES[index - 1])}
                        aria-label={`${t('kanban.moveBack')}: ${application.position || application.role}`}
                        className="h-6 w-6 p-0 text-xs"
                      >
                        ←
                      </Button>
                    )}
                    {index < PIPELINE_STAGES.length - 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => onMove(application, PIPELINE_STAGES[index + 1])}
                        aria-label={`${t('kanban.moveForward')}: ${application.position || application.role}`}
                        className="h-6 w-6 p-0 text-xs"
                      >
                        →
                      </Button>
                    )}
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      onClick={() => onDelete(application)}
                      aria-label={`${t('kanban.delete')}: ${application.position || application.role}`}
                      className="h-6 w-6 p-0"
                    >
                      <XIcon className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </article>
              ))
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Application tracker: quick-add form plus the Kanban pipeline.
 * Data access is owned by the parent via useApplications so the
 * job-discovery panel can add to the same store.
 */
export default function ApplicationTracker({ session, applicationsBundle }) {
  const { t } = useI18n();
  const { report } = useStatus();
  const { applications, loading, create, move, remove } = applicationsBundle;
  const [company, setCompany] = useState('');
  const [role, setRole] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleAddApplication(event) {
    event.preventDefault();

    if (!session) {
      report(t('status.signInRequired'), t('summary.signInToTrack'));
      return;
    }

    if (!company.trim() || !role.trim()) {
      report(t('status.searchRequired'), t('summary.enterSearch'));
      return;
    }

    setSubmitting(true);
    try {
      const created = await create({ company, position: role, status: 'applied' });
      report(t('status.applicationTracked'), t('summary.addedApplication', {
        position: created.position,
        company: created.company,
      }));
      setCompany('');
      setRole('');
    } catch (error) {
      report(t('status.trackerUnavailable'), error.message || t('summary.unableToTrack'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleMove(application, nextStage) {
    try {
      await move(application.id, nextStage);
    } catch (error) {
      report(t('status.trackerUnavailable'), error.message || t('summary.unableToTrack'));
    }
  }

  async function handleDelete(application) {
    try {
      await remove(application.id);
    } catch (error) {
      report(t('status.trackerUnavailable'), error.message || t('summary.unableToTrack'));
    }
  }

  return (
    <Card className="@container w-full">
      <CardHeader>
        <CardTitle>{t('tracker.title')}</CardTitle>
        <CardDescription>{t('tracker.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AuthGuard session={session}>
          <form onSubmit={handleAddApplication} className="grid gap-4 @sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="tracker-company">{t('tracker.company')}</Label>
              <Input
                id="tracker-company"
                value={company}
                onChange={(event) => setCompany(event.target.value)}
                placeholder={t('tracker.companyPlaceholder')}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="tracker-role">{t('tracker.role')}</Label>
              <Input
                id="tracker-role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
                placeholder={t('tracker.rolePlaceholder')}
              />
            </div>
            <Button
              type="submit"
              disabled={submitting}
              className="sm:col-span-2"
            >
              {submitting ? t('tracker.tracking') : t('tracker.track')}
            </Button>
          </form>
          {loading && applications.length === 0 ? (
            <LoadingState label={t('tracker.loading')} />
          ) : (
            <KanbanBoard
              applications={applications}
              onMove={handleMove}
              onDelete={handleDelete}
              t={t}
            />
          )}
        </AuthGuard>
        {!session && <EmptyState label={t('tracker.empty')} />}
      </CardContent>
    </Card>
  );
}
