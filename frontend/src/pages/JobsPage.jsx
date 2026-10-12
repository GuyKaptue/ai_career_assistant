import React from 'react';

import { useSession } from '../hooks/useSession';
import WorkspaceShell from '../components/WorkspaceShell';
import JobDiscovery from '../features/jobs/JobDiscovery';
import ApplicationTracker from '../features/tracker/ApplicationTracker';
import { useApplications } from '../hooks/useApplications';

/**
 * Job discovery page. Both panels share the same application store so a role
 * found in discovery can be pushed straight into the tracker.
 */
export default function JobsPage() {
  const { session } = useSession();
  const applications = useApplications(session);

  return (
    <WorkspaceShell titleKey="nav.jobs">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <JobDiscovery session={session} onCreateApplication={applications.create} />
        <ApplicationTracker session={session} applicationsBundle={applications} />
      </div>
    </WorkspaceShell>
  );
}
