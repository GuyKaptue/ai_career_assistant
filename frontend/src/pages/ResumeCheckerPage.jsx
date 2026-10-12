import React from 'react';

import { useSession } from '../hooks/useSession';
import WorkspaceShell from '../components/WorkspaceShell';
import ResumeChecker from '../features/resume-checker/ResumeChecker';

/**
 * Resume / ATS checker page.
 */
export default function ResumeCheckerPage() {
  const { session } = useSession();

  return (
    <WorkspaceShell titleKey="ats.title">
      <ResumeChecker session={session} onScore={() => {}} />
    </WorkspaceShell>
  );
}
