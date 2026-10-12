import React, { useState } from 'react';

import { supabase } from '../../lib/supabase';
import { useI18n } from '../../i18n';
import { useStatus } from '../../hooks/useStatus';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';

/**
 * Supabase auth panel. Owns its email/password/mode state and
 * reports authentication outcomes to the global status channel.
 */
export default function AuthPanel({ session, authLoading }) {
  const { t } = useI18n();
  const { report } = useStatus();
  const [authMode, setAuthMode] = useState('sign-in');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleAuthSubmit(event) {
    event.preventDefault();

    if (!authEmail || !authPassword) {
      report(t('status.authenticationRequired'), t('summary.enterCredentials'));
      return;
    }

    setSubmitting(true);
    report(t('status.authenticating'));
    try {
      if (authMode === 'sign-up') {
        const { error } = await supabase.auth.signUp({ email: authEmail, password: authPassword });
        if (error) {
          throw error;
        }
        report(t('status.ready'), t('summary.checkEmail'));
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email: authEmail,
          password: authPassword,
        });
        if (error) {
          throw error;
        }
        report(t('status.ready'), t('summary.signedIn'));
      }
      setAuthEmail('');
      setAuthPassword('');
    } catch (error) {
      report(t('status.authenticationFailed'), error.message || t('summary.unableToAuth'));
    } finally {
      setSubmitting(false);
    }
  }

  if (session) {
    return (
      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-lg">{t('auth.signedIn')}</CardTitle>
          <CardDescription>{session.user?.email || 'Authenticated user'}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="ghost"
            onClick={() => supabase.auth.signOut()}
            className="w-full"
          >
            {t('auth.signOut')}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="text-lg">
          {authMode === 'sign-up' ? t('auth.signUp') : t('auth.signIn')}
        </CardTitle>
        <CardDescription>
          {authMode === 'sign-up' ? t('auth.createAccountPrompt') : t('auth.signInPrompt')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleAuthSubmit} className="grid gap-4">
          <Input
            type="email"
            value={authEmail}
            onChange={(event) => setAuthEmail(event.target.value)}
            placeholder={t('auth.email')}
            aria-label={t('auth.email')}
            autoComplete="email"
          />
          <Input
            type="password"
            value={authPassword}
            onChange={(event) => setAuthPassword(event.target.value)}
            placeholder={t('auth.password')}
            aria-label={t('auth.password')}
            autoComplete="current-password"
          />
          <select
            value={authMode}
            onChange={(event) => setAuthMode(event.target.value)}
            aria-label={t('auth.mode')}
            className="w-full rounded-lg bg-background px-3 py-2 text-sm shadow-inset ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
          >
            <option value="sign-in">{t('auth.signIn')}</option>
            <option value="sign-up">{t('auth.signUp')}</option>
          </select>
          <Button
            type="submit"
            disabled={authLoading || submitting}
            className="w-full"
          >
            {authLoading || submitting
              ? t('auth.loading')
              : authMode === 'sign-up'
                ? t('auth.createAccount')
                : t('auth.signIn')}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
