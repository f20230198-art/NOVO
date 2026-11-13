import type { DaySummary, HourRisk, Level } from '../../lib/types';

export const MIN = 60 * 1000;
export const HALF_HOUR = 30 * MIN;
export const HOUR = 60 * MIN;

/** One hour on the timeline. `hour` is null when the server sent no forecast for it. */
export type Slot = { start: number; hour: HourRisk | null };

/** The server's forecast hour that covers `ms`, or null. Levels are read, never computed. */
export function hourAt(hours: HourRisk[], ms: number): HourRisk | null {
  return (
    hours.find((h) => {
      const start = new Date(h.time).getTime();
      return start <= ms && ms < start + HOUR;
    }) ?? null
  );
}

/** Whole-hour slots covering [from, to). */
export function slotsBetween(hours: HourRisk[], from: number, to: number): Slot[] {
  const slots: Slot[] = [];
  const first = Math.floor(from / HOUR) * HOUR;
  for (let s = first; s < to && slots.length < 72; s += HOUR) {
    slots.push({ start: s, hour: hourAt(hours, s) });
  }
  return slots;
}

/** What the fisher should be told about the hours they will be at sea. */
export type PlanRisk = {
  /** First hour at sea the server marked UNSAFE. */
  unsafe: Slot | null;
  /** First hour at sea the server marked CAUTION. */
  caution: Slot | null;
  /** First hour at sea with no forecast at all (treated as CAUTION at best, never SAFE). */
  unknown: Slot | null;
};

export function planRisk(slots: Slot[]): PlanRisk {
  return {
    unsafe: slots.find((s) => s.hour?.level === 'UNSAFE') ?? null,
    caution: slots.find((s) => s.hour?.level === 'CAUTION') ?? null,
    unknown: slots.find((s) => !s.hour) ?? null,
  };
}

/** Level shown for a slot. Missing data is shown as unknown, never SAFE. */
export function slotLevel(slot: Slot): Level | null {
  return slot.hour?.level ?? null;
}

export function roundUpToHalfHour(ms: number): number {
  return Math.ceil(ms / HALF_HOUR) * HALF_HOUR;
}

/** 'YYYY-MM-DD' of a time in the phone's own time zone, to match `DaySummary.date`. */
export function localDate(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Midnight (local) of a 'YYYY-MM-DD' day. */
export function dayStart(isoDate: string): number {
  return new Date(`${isoDate}T00:00:00`).getTime();
}

/**
 * Departure to offer when a day is picked: the start of the server's safe window, or "now" for
 * today if the window has already begun. Days without a window get no suggestion (null).
 */
export function suggestedDeparture(day: DaySummary, now: number): number | null {
  if (!day.window) return null;
  const start = new Date(day.window.start).getTime();
  const end = new Date(day.window.return_by).getTime();
  if (end <= now) return null;
  // The window has begun (the server sets its start to "now"): leave now.
  return start <= now + 15 * MIN ? now : start;
}

/**
 * Return time to offer: the server's "be back by" for that day, if it is after departure.
 * The server's return-by never falls in an UNSAFE hour, so this never suggests one.
 */
export function suggestedReturn(day: DaySummary, departAt: number): number | null {
  if (!day.return_by) return null;
  const back = new Date(day.return_by).getTime();
  return back > departAt + HALF_HOUR ? back : null;
}

/**
 * Return time to pre-fill when the server gave no "be back by": the longest trip of up to
 * 4 hours whose hours contain nothing UNSAFE. Falls back to one hour (the warning then shows).
 */
export function defaultReturn(hours: HourRisk[], departAt: number): number {
  for (let h = 4; h >= 1; h--) {
    const back = roundUpToHalfHour(departAt + h * HOUR);
    if (!planRisk(slotsBetween(hours, departAt, back)).unsafe) return back;
  }
  return roundUpToHalfHour(departAt + HOUR);
}
