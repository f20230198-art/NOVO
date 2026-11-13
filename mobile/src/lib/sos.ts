import * as SMS from 'expo-sms';
import { Linking } from 'react-native';

import type { Translate } from '../i18n';
import { api } from './api';
import { formatClock } from './format';
import { getFix, mapsLink, type Point } from './location';
import type { Contact, Profile, Trip } from './types';

export const COAST_GUARD = '1554';

export type SosResult = 'opened' | 'no-sms' | 'no-contacts';

/** Open the dialler with the Coast Guard search-and-rescue line. It is a voice line, not SMS. */
export function callCoastGuard(): void {
  Linking.openURL(`tel:${COAST_GUARD}`).catch(() => {});
}

/**
 * SOS: device SMS first, backend second.
 *
 * The SMS composer opens addressed to the emergency contacts with a map link. The backend
 * call is fired without waiting for it, so SOS does not depend on the server or on mobile
 * data. It does still need a phone signal: an SMS cannot leave a phone that has none.
 *
 * The message always says how good the position is: a fresh GPS fix, the last known
 * position with its time, or "position unknown" with the home harbour for reference.
 * The Coast Guard is not an SMS recipient (1554 is a voice line, and adding a short code
 * can turn the text into a group MMS that needs data); the SOS button offers a call instead.
 */
export async function sendSos(profile: Profile, contacts: Contact[], t: Translate, trip?: Trip | null): Promise<SosResult> {
  const home: Point = { lat: profile.home_lat, lon: profile.home_lon };
  const fix = await getFix(6000);

  let position = home;
  let kind: 'gps' | 'last_known' | 'home' = 'home';
  let seen: Date | null = null;
  if (fix?.fresh) {
    position = fix.point;
    kind = 'gps';
  } else if (fix) {
    position = fix.point;
    kind = 'last_known';
    seen = fix.at;
  } else if (trip && trip.last_lat !== null && trip.last_lon !== null) {
    position = { lat: trip.last_lat, lon: trip.last_lon };
    kind = 'last_known';
    seen = trip.last_ping_at ? new Date(trip.last_ping_at) : null;
  }

  // Best effort. Never awaited, never allowed to block the SMS.
  if (profile.token) api.sos(position.lat, position.lon, kind).catch(() => {});

  const common = { name: profile.name, boat: t(`boat_${profile.boat_type}`), link: mapsLink(position), time: formatClock(new Date()) };
  const message =
    kind === 'gps'
      ? t('sosMessage', common)
      : kind === 'last_known'
        ? t('sosMessageLastKnown', { ...common, seen: seen ? formatClock(seen) : '?' })
        : t('sosMessageNoFix', { ...common, harbour: profile.home_name });

  const numbers = Array.from(new Set(contacts.map((c) => c.phone.trim()).filter(Boolean)));
  if (numbers.length === 0) return 'no-contacts';

  try {
    if (await SMS.isAvailableAsync()) {
      await SMS.sendSMSAsync(numbers, message);
      return 'opened';
    }
  } catch {
    // fall through to the sms: link
  }
  try {
    await Linking.openURL(`sms:${numbers.join(',')}?body=${encodeURIComponent(message)}`);
    return 'opened';
  } catch {
    return 'no-sms';
  }
}
