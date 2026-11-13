import type { StringKey, Translate } from '../../i18n';

/**
 * Times, durations, days, units and compass points for the trip screens, in the fisher's
 * language. Every word comes from t(); only the digits are formatted here.
 */

/** Part of the day for an hour 0–23. English shows AM/PM; Malayalam says morning, noon, evening, night. */
function periodKey(hour: number): StringKey {
  if (hour < 4) return 'period_0_3';
  if (hour < 12) return 'period_4_11';
  if (hour < 15) return 'period_12_14';
  if (hour < 19) return 'period_15_18';
  return 'period_19_23';
}

/** '5:30 AM' / 'രാവിലെ 5:30'. */
export function clock(t: Translate, date: Date): string {
  const h = date.getHours();
  const m = date.getMinutes();
  return t('clockFmt', {
    h: h % 12 || 12,
    mm: m === 0 ? '' : `:${String(m).padStart(2, '0')}`,
    p: t(periodKey(h)),
  });
}

/** Short hour for the timeline axis: '5a' / '5'. */
export function axisHour(t: Translate, date: Date): string {
  const h = date.getHours();
  return t('axisHourFmt', { h12: h % 12 || 12, ap: h < 12 ? t('axisAm') : t('axisPm'), h24: h });
}

/** '2 h 05 min' / '12 min' (sign ignored). */
export function duration(t: Translate, ms: number): string {
  const total = Math.floor(Math.abs(ms) / 60000);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h > 0 ? t('durHM', { h, m: String(m).padStart(2, '0') }) : t('durM', { m });
}

const DOW: StringKey[] = ['dow0', 'dow1', 'dow2', 'dow3', 'dow4', 'dow5', 'dow6'];

/** 'Fri 13' / 'വെള്ളി 13' from a 'YYYY-MM-DD' day. */
export function dayShort(t: Translate, isoDate: string): string {
  const d = new Date(`${isoDate}T12:00:00`);
  return t('dayFmt', { dow: t(DOW[d.getDay()]), d: d.getDate() });
}

const COMPASS: Record<string, StringKey> = {
  N: 'dir_N',
  NE: 'dir_NE',
  E: 'dir_E',
  SE: 'dir_SE',
  S: 'dir_S',
  SW: 'dir_SW',
  W: 'dir_W',
  NW: 'dir_NW',
};

/** Compass point the server sends ('SW') in the fisher's language. Unknown codes are shown as sent. */
export function compass(t: Translate, code: string | null | undefined): string {
  if (!code) return '';
  const key = COMPASS[code];
  return key ? t(key) : code;
}

export const metres = (t: Translate, v: string) => t('unitM', { v });
export const kmh = (t: Translate, v: string) => t('unitKmh', { v });
