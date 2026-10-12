import React from 'react';

import { useSession } from '../hooks/useSession';
import WorkspaceShell from '../components/WorkspaceShell';
import { useApplications } from '../hooks/useApplications';
import ApplicationTracker from '../features/tracker/ApplicationTracker';

/**
 * Application tracker page. Also the destination for roles saved from job
 * discovery, since both pages write to the same application store.
 */
export default function TrackerPage() {
  const { session } = useSession();
  const applications = useApplications(session);

  return (
    <WorkspaceShell titleKey="nav.tracker">
      <ApplicationTracker session={session} applicationsBundle={applications} />
    </WorkspaceShell>
  );
}
