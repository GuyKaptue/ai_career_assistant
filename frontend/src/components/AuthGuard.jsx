import React from 'react';
import { useI18n } from '../i18n';
import { useSession } from '../hooks/useSession';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';

/**
 * Renders a sign-in prompt when no session exists. Features that
 * require an account wrap their interactive content in this guard
 * so the auth state is explicit (FE-03 auth states).
 *
 * Accepts an optional session prop; falls back to the global
 * session hook when omitted.
 */
export default function AuthGuard({ session: sessionProp, children }) {
  const { t } = useI18n();
  const { session: hookSession } = useSession();
  const session = sessionProp !== undefined ? sessionProp : hookSession;

  if (session) {
    return children;
  }

  return (
    <Card className="bg-amber-50/60 dark:bg-amber-900/15" role="note">
      <CardHeader>
        <CardTitle className="text-amber-700/80 dark:text-amber-400/80">
          {t('status.signInRequired')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <CardDescription>{t('summary.signInToTrack')}</CardDescription>
      </CardContent>
    </Card>
  );
}
