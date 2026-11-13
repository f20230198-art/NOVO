/** '6 AM', '10:30 AM' in the phone's own time zone. */
export function formatClock(date: Date): string {
  const h = date.getHours();
  const m = date.getMinutes();
  const h12 = h % 12 || 12;
  const suffix = h < 12 ? 'AM' : 'PM';
  return m === 0 ? `${h12} ${suffix}` : `${h12}:${String(m).padStart(2, '0')} ${suffix}`;
}

export function formatHour(hour: number): string {
  const h12 = hour % 12 || 12;
  return `${h12}${hour < 12 ? 'a' : 'p'}`;
}

/** '2 h 05 min' or '12 min' from a number of milliseconds (sign ignored). */
export function formatDuration(ms: number): string {
  const totalMin = Math.floor(Math.abs(ms) / 60000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h > 0 ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`;
}

export function formatDay(isoDate: string): string {
  const d = new Date(`${isoDate}T12:00:00`);
  return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()] + ' ' + d.getDate();
}

export function num(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? '–' : value.toFixed(digits).replace(/\.0$/, '');
}

/** Initial bearing in degrees from point 1 to point 2. */
export function bearing(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const rad = Math.PI / 180;
  const y = Math.sin((lon2 - lon1) * rad) * Math.cos(lat2 * rad);
  const x =
    Math.cos(lat1 * rad) * Math.sin(lat2 * rad) - Math.sin(lat1 * rad) * Math.cos(lat2 * rad) * Math.cos((lon2 - lon1) * rad);
  return ((Math.atan2(y, x) / rad) + 360) % 360;
}

/** Wind (or current) component along a course. `fromDeg` is where the wind blows FROM: positive = head wind. */
export function along(speed: number | null | undefined, fromDeg: number | null | undefined, course: number): number | null {
  if (speed == null || fromDeg == null) return null;
  return speed * Math.cos(((fromDeg - course) * Math.PI) / 180);
}
