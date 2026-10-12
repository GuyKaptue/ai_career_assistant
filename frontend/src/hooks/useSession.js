import { useEffect, useState } from 'react';

import { supabase } from '../lib/supabase';
import { debugLog } from '../lib/debug';

export function useSession() {
  const [session, setSession] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadSession() {
      const {
        data: { session: currentSession },
      } = await supabase.auth.getSession();
      debugLog('auth', 'initial session loaded', { hasSession: Boolean(currentSession) });
      if (isMounted) {
        setSession(currentSession);
        setAuthLoading(false);
      }
    }

    loadSession();

    const { data: authListener } = supabase.auth.onAuthStateChange((event, nextSession) => {
      debugLog('auth', 'auth state change', { event, hasSession: Boolean(nextSession) });
      if (isMounted) {
        setSession(nextSession);
        setAuthLoading(false);
      }
    });

    return () => {
      isMounted = false;
      authListener.subscription.unsubscribe();
    };
  }, []);

  return { session, authLoading };
}
