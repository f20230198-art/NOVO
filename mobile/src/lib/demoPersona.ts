import { useCallback } from 'react';

import { getBaseUrl } from './api';
import { useApp } from './store';
import type { Contact, Profile } from './types';

/** What `POST /demo/persona/adopt` returns: the demo fisher's own profile (with token) and contacts. */
export type DemoPersona = { profile: Profile; contacts: Contact[]; boat: string; demo: true };

async function fetchDemoPersona(): Promise<DemoPersona> {
  const resp = await fetch(`${getBaseUrl()}/demo/persona/adopt`, { method: 'POST', headers: { Accept: 'application/json' } });
  if (!resp.ok) {
    let detail = `Server error (${resp.status})`;
    try {
      const body = await resp.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      // keep the generic message
    }
    throw new Error(detail);
  }
  return (await resp.json()) as DemoPersona;
}

/**
 * Turn this phone into the demo fisher (Shibu Lopez, Vizhinjam). The backend must have the persona
 * loaded first (`POST /demo/persona` with the admin key). Replaces the saved profile and contacts.
 */
export function useAdoptDemoPersona() {
  const { completeOnboarding } = useApp();
  return useCallback(async () => {
    const persona = await fetchDemoPersona();
    await completeOnboarding(persona.profile, persona.contacts);
    return persona;
  }, [completeOnboarding]);
}
