import React, { useState } from 'react';

import { useTheme } from '../hooks/useTheme';
import { useI18n } from '../i18n';
import { useAuthDialog } from '../hooks/useAuthDialog';
import { useSession } from '../hooks/useSession';
import { AUTO_MODEL, useModels } from '../hooks/useModels';
import { supabase } from '../lib/supabase';
import { cn } from '../lib/utils';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Select } from './ui/select';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { CpuIcon, MonitorIcon, MoonIcon, SlidersIcon, SunIcon, UserIcon } from './icons';

/**
 * The application's one Settings dialog (mounted once, in AppShell, and opened
 * from the account menu — see components/UserMenu.jsx).
 *
 * Same card as every other dialog (components/ui/dialog.jsx):
 *   HEADER   "Settings" + close (X)
 *   CONTENT  section navigation + the selected section
 *   FOOTER   Done
 *
 * Sections (a vertical list on wide screens, a scrolling tab row on phones)
 *   General   — colour theme and interface language
 *   AI models — the model picker; "Auto" lets the backend choose per task
 *   Account   — sign in / sign out
 *
 * Workspace navigation (documents, resume checker, jobs, tracker) lives in the
 * sidebar, like Claude's own nav, so it is not repeated here.
 */
const SECTIONS = [
  { id: 'general', Icon: SlidersIcon, i18nKey: 'settings.general', descriptionKey: 'settings.generalDescription' },
  { id: 'models', Icon: CpuIcon, i18nKey: 'settings.aiModels', descriptionKey: 'settings.aiModelsDescription' },
  { id: 'account', Icon: UserIcon, i18nKey: 'settings.account', descriptionKey: 'settings.accountDescription' },
];

const THEME_OPTIONS = [
  { id: 'light', Icon: SunIcon },
  { id: 'dark', Icon: MoonIcon },
  { id: 'system', Icon: MonitorIcon },
];

/** Endonyms, so a user can always find their own language. */
const LOCALE_NAMES = { en: 'English', de: 'Deutsch', fr: 'Français' };

export default function SettingsDialog({ open, onOpenChange }) {
  const { t, locale, setLocale, availableLocales = [] } = useI18n();
  const { theme, setTheme } = useTheme();
  const { openAuth } = useAuthDialog();
  const { session } = useSession();
  const { models, selectedModel, setSelectedModel, autoDefaultModel, loading: modelsLoading } = useModels(session);
  const [section, setSection] = useState('general');

  const active = SECTIONS.find((entry) => entry.id === section) || SECTIONS[0];

  /** Sign-in opens its own dialog; close Settings first so they never stack. */
  function startAuth(mode) {
    onOpenChange?.(false);
    openAuth(mode);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="2xl" className="sm:h-[34rem]">
      <DialogHeader>
        <DialogTitle>{t('chat.settings')}</DialogTitle>
      </DialogHeader>

      <DialogContent className="gap-5 sm:flex-row sm:gap-8 sm:overflow-hidden">
        {/* Section navigation */}
        <nav
          aria-label={t('settings.sections')}
          className="flex shrink-0 gap-1 sm:w-44 sm:flex-col"
        >
          {SECTIONS.map(({ id, Icon, i18nKey }) => (
            <button
              key={id}
              type="button"
              onClick={() => setSection(id)}
              aria-current={section === id ? 'true' : undefined}
              className={cn(
                'flex min-w-0 flex-1 items-center justify-center gap-2 rounded-lg px-2 py-2 text-sm transition-colors sm:flex-none sm:justify-start sm:gap-2.5 sm:px-3 sm:text-left',
                section === id
                  ? 'bg-accent font-medium text-foreground'
                  : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="truncate">{t(i18nKey)}</span>
            </button>
          ))}
        </nav>

        {/* Selected section */}
        <section
          aria-labelledby={`settings-${active.id}`}
          className="min-w-0 flex-1 space-y-5 sm:min-h-0 sm:overflow-y-auto sm:pr-1"
        >
          <header className="space-y-1">
            <h3 id={`settings-${active.id}`} className="text-base font-semibold">
              {t(active.i18nKey)}
            </h3>
            <p className="text-sm text-muted-foreground">{t(active.descriptionKey)}</p>
          </header>

          {active.id === 'general' && (
            <div className="space-y-6">
              <div className="space-y-2.5">
                <div className="text-sm font-medium">{t('settings.themeTitle')}</div>
                <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t('settings.themeTitle')}>
                  {THEME_OPTIONS.map(({ id, Icon }) => (
                    <button
                      key={id}
                      type="button"
                      role="radio"
                      aria-checked={theme === id}
                      onClick={() => setTheme(id)}
                      className={cn(
                        'flex flex-col items-center gap-1.5 rounded-xl border px-3 py-3 text-sm transition-colors',
                        theme === id
                          ? 'border-primary bg-primary/10 font-medium text-foreground'
                          : 'border-border text-muted-foreground hover:bg-accent hover:text-foreground',
                      )}
                    >
                      <Icon className="h-5 w-5" />
                      {t(`settings.theme.${id}`)}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">{t('settings.themeHint')}</p>
              </div>

              <Label>
                <span>{t('settings.language')}</span>
                <Select value={locale} onChange={(event) => setLocale(event.target.value)}>
                  {availableLocales.map((code) => (
                    <option key={code} value={code}>
                      {LOCALE_NAMES[code] || code}
                    </option>
                  ))}
                </Select>
              </Label>
            </div>
          )}

          {active.id === 'models' && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">{t('chat.modelAutoExplain')}</p>
              <Label>
                <span>{t('chat.model')}</span>
                <Select
                  value={selectedModel ?? AUTO_MODEL}
                  onChange={(event) => setSelectedModel(event.target.value || null)}
                  disabled={modelsLoading || models.length === 0}
                >
                  <option value={AUTO_MODEL}>
                    {autoDefaultModel ? `${t('chat.modelAuto')} · ${autoDefaultModel}` : t('chat.modelAuto')}
                  </option>
                  {models.map((model) => (
                    <option key={model.model_id} value={model.model_id}>
                      {model.model_id}
                      {model.chat_compatible === false ? ` (${t('settings.modelUnavailable')})` : ''}
                    </option>
                  ))}
                </Select>
              </Label>
              {models.length === 0 && !modelsLoading && (
                <p className="text-xs text-muted-foreground">{t('chat.noModels')}</p>
              )}
            </div>
          )}

          {active.id === 'account' && (
            <div className="space-y-4">
              {session ? (
                <>
                  <div className="flex items-center gap-3 rounded-xl border border-border p-3">
                    <span
                      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-foreground text-sm font-semibold text-background"
                      aria-hidden="true"
                    >
                      {(session.user?.user_metadata?.name || session.user?.email || '?').charAt(0).toUpperCase()}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{session.user?.email}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {session.user?.user_metadata?.name || t('auth.name')}
                      </p>
                    </div>
                  </div>
                  <Button variant="outline" onClick={() => supabase.auth.signOut()}>
                    {t('auth.signOut')}
                  </Button>
                </>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">{t('settings.signInPrompt')}</p>
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={() => startAuth('sign-in')}>{t('auth.signIn')}</Button>
                    <Button variant="outline" onClick={() => startAuth('sign-up')}>
                      {t('auth.signUp')}
                    </Button>
                  </div>
                </>
              )}
            </div>
          )}
        </section>
      </DialogContent>

      <DialogFooter>
        <Button onClick={() => onOpenChange?.(false)}>{t('common.done', 'Done')}</Button>
      </DialogFooter>
    </Dialog>
  );
}
