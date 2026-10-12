import React, { useCallback, useEffect, useId, useRef, useState } from 'react';

import { supabase } from '../../lib/supabase';
import { apiRequest } from '../../lib/api';
import { debugLog } from '../../lib/debug';
import { useI18n } from '../../i18n';
import { useStatus } from '../../hooks/useStatus';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../components/ui/dialog';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD = 6;

/**
 * Verify (and if needed create) the `public.profiles` row for the signed-in
 * user before the app treats them as authenticated.
 *
 * Supabase creates the auth.users row on signUp/signIn, but the profile row
 * is created by a DB trigger (or by this fallback when the trigger is
 * missing). A signed-in user without a profile row is the "signed up but no
 * user record" bug, so this runs before the dialog reports success:
 *
 *   1. GET /api/v1/profiles/<id> — row already exists (trigger fired)?
 *   2. POST /api/v1/profiles — create it (backend derives user_id/email
 *      from the JWT, so no client-supplied identity is trusted).
 *   3. GET again — confirm the row really persisted.
 *
 * Any failure propagates: the caller signs the session back out rather than
 * showing the user as signed in without a database record.
 */
async function ensureProfileRow(session, fullName) {
  const userId = session?.user?.id;
  debugLog('auth', 'verify profile row', { userId });
  try {
    await apiRequest(`/api/v1/profiles/${userId}`, { session });
    debugLog('auth', 'profile row exists', { userId });
    return;
  } catch (error) {
    // 404 (missing row) and transient failures both land here; the POST
    // below distinguishes them by also failing loudly if the backend is down.
    debugLog('auth', 'profile row missing or unreadable', { userId, message: error?.message });
  }
  await apiRequest('/api/v1/profiles', {
    method: 'POST',
    session,
    body: { full_name: fullName || '' },
  });
  debugLog('auth', 'profile row created', { userId });
  await apiRequest(`/api/v1/profiles/${userId}`, { session });
  debugLog('auth', 'profile row verified', { userId });
}


/**
 * Shared auth dialog: sign in and sign up live in one dialog as two tabs, so
 * there is a single form to learn rather than two competing dialogs.
 *
 * Accessibility and interaction:
 *   - proper ARIA tabs (roles, aria-selected, aria-controls, arrow-key move)
 *   - labels bound to inputs, inline validation announced with role="alert"
 *   - submit shows a loading state and disables every field while pending
 *   - the underlying Dialog provides the focus trap, Escape, aria-modal and
 *     the fade/scale animation (see components/ui/dialog.jsx)
 */
export default function AuthDialogs({ open, mode = 'sign-in', onOpenChange, onSuccess, onModeChange }) {
  const { t } = useI18n();
  const { report } = useStatus();

  const [activeTab, setActiveTab] = useState(mode === 'sign-up' ? 'sign-up' : 'sign-in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState({});

  const titleId = useId();
  const tabRefs = useRef({});
  const isSignUp = activeTab === 'sign-up';
  const loading = submitting;

  // Follow an external mode change (e.g. the header's "Sign up" link).
  useEffect(() => {
    if (!open) return undefined;
    setActiveTab(mode === 'sign-up' ? 'sign-up' : 'sign-in');
    return undefined;
  }, [mode, open]);

  // Clear everything when the dialog closes so no credentials linger.
  useEffect(() => {
    if (open) return undefined;
    setEmail('');
    setPassword('');
    setName('');
    setConfirmPassword('');
    setShowPassword(false);
    setShowConfirmPassword(false);
    setErrors({});
    setSubmitting(false);
    return undefined;
  }, [open]);

  function switchTab(next) {
    setActiveTab(next);
    setErrors({});
    onModeChange?.(next);
  }

  // Arrow-key navigation between tabs, per the ARIA tabs pattern.
  const handleTabKeyDown = useCallback(
    (event) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      const next = activeTab === 'sign-in' ? 'sign-up' : 'sign-in';
      switchTab(next);
      window.setTimeout(() => tabRefs.current[next]?.focus(), 0);
    },
    [activeTab],
  );

  function validate() {
    const next = {};
    if (!name.trim() && isSignUp) next.name = t('auth.nameRequired');
    if (!email.trim()) {
      next.email = t('auth.emailRequired');
    } else if (!EMAIL_PATTERN.test(email.trim())) {
      next.email = t('auth.emailInvalid');
    }
    if (!password) {
      next.password = t('auth.passwordRequired');
    } else if (isSignUp && password.length < MIN_PASSWORD) {
      next.password = t('auth.passwordTooShort', { count: MIN_PASSWORD });
    }
    if (isSignUp && password !== confirmPassword) {
      next.confirmPassword = t('auth.passwordsDontMatch');
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (loading) return;
    if (!validate()) return;

    setSubmitting(true);
    report(t('status.authenticating'));
    const trimmedEmail = email.trim();

    try {
      if (isSignUp) {
        debugLog('auth', 'signUp request', { email: trimmedEmail, hasName: Boolean(name.trim()) });
        const { error, data } = await supabase.auth.signUp({
          email: trimmedEmail,
          password,
          options: { data: { name: name.trim() } },
        });
        debugLog('auth', 'signUp response', {
          error: error?.message ?? null,
          userId: data?.user?.id ?? null,
          hasSession: Boolean(data?.session),
        });
        if (error) throw error;
        if (!data?.session) {
          // Email confirmation required: the auth row (and, via the DB
          // trigger, the profile row) already exist, but there is no token
          // to verify with yet — the user confirms by email first.
          debugLog('auth', 'signUp: email confirmation required, deferring profile verification');
          report(t('status.ready'), t('summary.checkEmail'));
          onSuccess?.('sign-up');
        } else {
          await ensureProfileRow(data.session, name.trim());
          report(t('status.ready'), t('summary.signedIn'));
          onSuccess?.('sign-up');
        }
      } else {
        debugLog('auth', 'signIn request', { email: trimmedEmail });
        const { error, data } = await supabase.auth.signInWithPassword({
          email: trimmedEmail,
          password,
        });
        debugLog('auth', 'signIn response', {
          error: error?.message ?? null,
          userId: data?.user?.id ?? null,
          hasSession: Boolean(data?.session),
        });
        if (error) throw error;
        // Self-heal: users registered before the trigger existed have no
        // profile row — create it now instead of leaving them broken.
        await ensureProfileRow(data.session, '');
        report(t('status.ready'), t('summary.signedIn'));
        onSuccess?.('sign-in');
      }
      onOpenChange?.(false);
    } catch (error) {
      debugLog('auth', 'submit failed', { message: error?.message });
      // Never show a user as signed in without a verified profiles row:
      // roll back the Supabase session and surface the error instead.
      await supabase.auth.signOut();
      const message = error?.message || t('summary.unableToAuth');
      setErrors({ form: message });
      report(t('status.authenticationFailed'), message);
    } finally {
      setSubmitting(false);
    }
  }

  const fieldClass = 'space-y-1.5';
  // The form doubles as the active tab panel; the footer submit button targets it by id.
  const formId = `auth-panel-${activeTab}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="md">
      {/* HEADER — title + description, close (X) is added by DialogHeader */}
      <DialogHeader>
        <DialogTitle id={titleId}>{t('auth.signInTitle')}</DialogTitle>
        <DialogDescription>{t('auth.dialogDescription')}</DialogDescription>
      </DialogHeader>

      {/* CONTENT — mode tabs and the form fields */}
      <DialogContent>
        {/* Tabs: Sign In | Sign Up */}
        <div
          role="tablist"
          aria-label={t('auth.tabListLabel')}
          className="flex shrink-0 gap-1 rounded-lg bg-muted p-1"
          onKeyDown={handleTabKeyDown}
        >
          {[
            { id: 'sign-in', label: t('auth.signIn') },
            { id: 'sign-up', label: t('auth.signUp') },
          ].map((tab) => (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[tab.id] = el;
              }}
              type="button"
              role="tab"
              id={`auth-tab-${tab.id}`}
              aria-selected={activeTab === tab.id}
              aria-controls={`auth-panel-${tab.id}`}
              tabIndex={activeTab === tab.id ? 0 : -1}
              onClick={() => switchTab(tab.id)}
              className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-card text-foreground shadow-soft'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <form
          id={formId}
          role="tabpanel"
          aria-labelledby={`auth-tab-${activeTab}`}
          onSubmit={handleSubmit}
          noValidate
          className="grid gap-4"
        >
          {isSignUp && (
            <div className={fieldClass}>
              <Label htmlFor="auth-name">{t('auth.name')}</Label>
              <Input
                id="auth-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('auth.namePlaceholder')}
                disabled={loading}
                autoComplete="name"
                aria-invalid={Boolean(errors.name)}
                aria-describedby={errors.name ? 'auth-name-error' : undefined}
              />
              {errors.name && (
                <p id="auth-name-error" role="alert" className="text-xs text-destructive">
                  {errors.name}
                </p>
              )}
            </div>
          )}

          <div className={fieldClass}>
            <Label htmlFor="auth-email">{t('auth.email')}</Label>
            <Input
              id="auth-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t('auth.emailPlaceholder')}
              disabled={loading}
              autoComplete="email"
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? 'auth-email-error' : undefined}
            />
            {errors.email && (
              <p id="auth-email-error" role="alert" className="text-xs text-destructive">
                {errors.email}
              </p>
            )}
          </div>

          <div className={fieldClass}>
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="auth-password">{t('auth.password')}</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowPassword((v) => !v)}
                className="-my-1 h-7 px-2 text-xs text-muted-foreground"
              >
                {showPassword ? t('auth.hide') : t('auth.show')}
              </Button>
            </div>
            <Input
              id="auth-password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t('auth.passwordPlaceholder')}
              disabled={loading}
              autoComplete={isSignUp ? 'new-password' : 'current-password'}
              aria-invalid={Boolean(errors.password)}
              aria-describedby={errors.password ? 'auth-password-error' : undefined}
            />
            {errors.password && (
              <p id="auth-password-error" role="alert" className="text-xs text-destructive">
                {errors.password}
              </p>
            )}
          </div>

          {isSignUp && (
            <div className={fieldClass}>
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="auth-confirm-password">{t('auth.confirmPassword')}</Label>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowConfirmPassword((v) => !v)}
                  className="-my-1 h-7 px-2 text-xs text-muted-foreground"
                >
                  {showConfirmPassword ? t('auth.hide') : t('auth.show')}
                </Button>
              </div>
              <Input
                id="auth-confirm-password"
                type={showConfirmPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder={t('auth.confirmPasswordPlaceholder')}
                disabled={loading}
                autoComplete="new-password"
                aria-invalid={Boolean(errors.confirmPassword)}
                aria-describedby={errors.confirmPassword ? 'auth-confirm-password-error' : undefined}
              />
              {errors.confirmPassword && (
                <p id="auth-confirm-password-error" role="alert" className="text-xs text-destructive">
                  {errors.confirmPassword}
                </p>
              )}
            </div>
          )}

          {errors.form && (
            <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {errors.form}
            </p>
          )}
        </form>
      </DialogContent>

      {/* FOOTER — the submit action (bound to the form above) and the legal note */}
      <DialogFooter className="sm:flex-col sm:items-stretch sm:justify-start">
        <Button type="submit" form={formId} disabled={loading} className="w-full" data-autofocus="true">
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span
                className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
                aria-hidden="true"
              />
              {t('auth.loading')}
            </span>
          ) : isSignUp ? (
            t('auth.createAccount')
          ) : (
            t('auth.signIn')
          )}
        </Button>
        <p className="text-center text-xs text-muted-foreground">{t('auth.termsNotice')}</p>
      </DialogFooter>
    </Dialog>
  );
}
