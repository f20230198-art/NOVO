import * as SMS from 'expo-sms';
import { Linking } from 'react-native';

import type { Translate } from '../i18n';
import { api } from './api';
import { formatClock } from './format';
import { getPosition, mapsLink } from './location';
import type { Contact, Profile } from './types';

export const COAST_GUARD = '1554';

/**
 * SOS: device SMS first, backend second.
 *
 * The SMS composer opens with every contact plus the Coast Guard and a map link.
 * The backend call is fired without waiting for it, so SOS works with the server
 * down or no mobile data. Returns 'opened', or 'no-sms' if the phone cannot send SMS.
 */
export async function sendSos(profile: Profile, contacts: Contact[], t: Translate): Promise<'opened' | 'no-sms'> {
  const home = { lat: profile.home_lat, lon: profile.home_lon };
  const position = (await getPosition(home, 4000)) ?? home;

  // Best effort. Never awaited, never allowed to block the SMS.
  if (profile.token) api.sos(position.lat, position.lon).catch(() => {});

  const message = t('sosMessage', {
    name: profile.name,
    boat: t(`boat_${profile.boat_type}`),
    link: mapsLink(position),
    time: formatClock(new Date()),
  });
  const numbers = Array.from(new Set([...contacts.map((c) => c.phone.trim()).filter(Boolean), COAST_GUARD]));

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
