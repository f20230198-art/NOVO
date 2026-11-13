import * as Location from 'expo-location';

export type Point = { lat: number; lon: number };

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  return Promise.race([promise, new Promise<null>((resolve) => setTimeout(() => resolve(null), ms))]);
}

/**
 * Best position we can get quickly: a fresh GPS fix if it arrives in time, else the
 * last known position, else the fallback (the home harbour). Never throws.
 */
export async function getPosition(fallback: Point | null, timeoutMs = 6000): Promise<Point | null> {
  try {
    let perm = await Location.getForegroundPermissionsAsync();
    if (!perm.granted && perm.canAskAgain) perm = await Location.requestForegroundPermissionsAsync();
    if (!perm.granted) return fallback;

    const fresh = await withTimeout(
      Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
      timeoutMs,
    ).catch(() => null);
    if (fresh) return { lat: fresh.coords.latitude, lon: fresh.coords.longitude };

    const last = await Location.getLastKnownPositionAsync().catch(() => null);
    if (last) return { lat: last.coords.latitude, lon: last.coords.longitude };
  } catch {
    // fall through to the fallback
  }
  return fallback;
}

export type Fix = { point: Point; fresh: boolean; at: Date };

const FRESH_MS = 3 * 60 * 1000;

/**
 * Position for SOS, with how much it can be trusted. `fresh` is a GPS fix from the last
 * few minutes; otherwise it is the phone's last known position and `at` says how old.
 * Null when the phone has no position at all. Never falls back to the home harbour:
 * a rescuer must not be sent there by mistake.
 */
export async function getFix(timeoutMs = 6000): Promise<Fix | null> {
  try {
    let perm = await Location.getForegroundPermissionsAsync();
    if (!perm.granted && perm.canAskAgain) perm = await Location.requestForegroundPermissionsAsync();
    if (!perm.granted) return null;

    const fresh = await withTimeout(
      Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
      timeoutMs,
    ).catch(() => null);
    if (fresh) return { point: { lat: fresh.coords.latitude, lon: fresh.coords.longitude }, fresh: true, at: new Date(fresh.timestamp) };

    const last = await Location.getLastKnownPositionAsync().catch(() => null);
    if (last) {
      const at = new Date(last.timestamp);
      return { point: { lat: last.coords.latitude, lon: last.coords.longitude }, fresh: Date.now() - at.getTime() < FRESH_MS, at };
    }
  } catch {
    // no position
  }
  return null;
}

const NEAR_HOME_KM = 100;

/**
 * Position to use for forecasts, trips and hazard reports.
 *
 * GPS when the phone is within 100 km of the home harbour, otherwise the harbour itself.
 * A fisher is always near their harbour; a phone that is far away (a demo in another
 * city, a visit inland) would otherwise ask for a sea forecast on dry land.
 * SOS does not use this: it always sends the real GPS position.
 */
export async function getWorkingPosition(home: Point, timeoutMs = 5000): Promise<Point> {
  const gps = await getPosition(null, timeoutMs);
  return gps && distanceKm(gps, home) <= NEAR_HOME_KM ? gps : home;
}

export function mapsLink(p: Point): string {
  return `https://maps.google.com/?q=${p.lat.toFixed(5)},${p.lon.toFixed(5)}`;
}

export function distanceKm(a: Point, b: Point): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}
