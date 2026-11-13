import { api } from './api';
import type { Point } from './location';
import { loadJson, saveJson } from './store';
import type { Trip } from './types';

/**
 * Positions recorded while the phone had no signal. When signal returns they are uploaded,
 * so the server knows how far out the boat went (the automatic SOS depends on it) and
 * where it was last seen.
 */
const KEY = 'seasafe.trackQueue';
const MAX_POINTS = 288; // one every 5 minutes for 24 hours

type Queued = { tripId: number; lat: number; lon: number; at: string };

export async function sendPosition(trip: Trip, point: Point): Promise<Trip | null> {
  const queue = ((await loadJson<Queued[]>(KEY)) ?? []).filter((q) => q.tripId === trip.id);
  queue.push({ tripId: trip.id, lat: point.lat, lon: point.lon, at: new Date().toISOString() });
  try {
    const updated =
      queue.length === 1
        ? await api.pingTrip(trip.id, point.lat, point.lon)
        : await api.uploadTrack(trip.id, queue.map(({ lat, lon, at }) => ({ lat, lon, at })));
    await saveJson(KEY, null);
    return updated;
  } catch {
    await saveJson(KEY, queue.slice(-MAX_POINTS));
    return null;
  }
}

export async function clearTrack(): Promise<void> {
  await saveJson(KEY, null);
}
