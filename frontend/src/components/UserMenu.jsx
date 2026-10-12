import React from 'react';

import { useSession } from '../hooks/useSession';
import { useI18n } from '../i18n';
import { useAuthDialog } from '../hooks/useAuthDialog';
import { useSettingsDialog } from '../hooks/useSettingsDialog';
import { useShell } from './shell-context';
import { supabase } from '../lib/supabase';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { ChevronUpDownIcon, GearIcon, LogInIcon, LogOutIcon, UserIcon } from './icons';

/** First letter of the name / email, for the avatar disc. */
function initialOf(session) {
  const source = session?.user?.user_metadata?.name || session?.user?.email || '';
  return source.trim().charAt(0).toUpperCase();
}

/**
 * Account row at the bottom of the sidebar (Claude's profile menu).
 *
 * This menu is the ONE place Settings can be opened from. Guests get the same
 * row with sign-in / sign-up; signed-in users additionally get sign out.
 */
export default function UserMenu() {
  const { session, authLoading } = useSession();
  const { t } = useI18n();
  const { openAuth } = useAuthDialog();
  const { openSettings } = useSettingsDialog();
  const { closeDrawer } = useShell();

  /** Dialogs open over the page, so a mobile drawer must get out of the way first. */
  const openAndCloseDrawer = (open) => () => {
    closeDrawer();
    open();
  };

  const signedIn = Boolean(session);
  const displayName = signedIn
    ? session.user?.user_metadata?.name || session.user?.email || t('auth.account', 'Account')
    : t('auth.guest', 'Guest');
  const subline = signedIn ? session.user?.email : t('auth.guestHint', 'Not signed in');

  async function handleLogout() {
    await supabase.auth.signOut();
  }

  return (
    <DropdownMenu className="block w-full">
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t('auth.accountMenu', 'Account menu')}
          className="flex w-full items-center gap-2.5 rounded-lg p-2 text-left transition-colors hover:bg-accent"
        >
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-sm font-semibold text-background"
            aria-hidden="true"
          >
            {signedIn ? initialOf(session) || <UserIcon className="h-4 w-4" /> : <UserIcon className="h-4 w-4" />}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium leading-tight text-foreground">{displayName}</span>
            <span className="block truncate text-xs leading-tight text-muted-foreground">{subline}</span>
          </span>
          <ChevronUpDownIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent side="top" align="stretch">
        {signedIn && (
          <>
            <div className="px-2.5 py-1.5">
              <div className="truncate text-sm font-medium">{session.user?.email}</div>
              <div className="truncate text-xs text-muted-foreground">
                {session.user?.user_metadata?.name || t('auth.name')}
              </div>
            </div>
            <DropdownMenuSeparator />
          </>
        )}

        <DropdownMenuItem onSelect={openAndCloseDrawer(openSettings)}>
          <GearIcon className="h-4 w-4 text-muted-foreground" />
          <span>{t('chat.settings')}</span>
        </DropdownMenuItem>

        {/* Sign-in state is unknown until the session settles; Settings never waits for it. */}
        {!authLoading && <DropdownMenuSeparator />}

        {authLoading ? null : signedIn ? (
          <DropdownMenuItem onSelect={handleLogout}>
            <LogOutIcon className="h-4 w-4 text-muted-foreground" />
            <span>{t('auth.signOut')}</span>
          </DropdownMenuItem>
        ) : (
          <>
            <DropdownMenuItem onSelect={openAndCloseDrawer(() => openAuth('sign-in'))}>
              <LogInIcon className="h-4 w-4 text-muted-foreground" />
              <span>{t('auth.signIn')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={openAndCloseDrawer(() => openAuth('sign-up'))}>
              <UserIcon className="h-4 w-4 text-muted-foreground" />
              <span>{t('auth.signUp')}</span>
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
