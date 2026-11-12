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
