import type { Advice, BoatType, Contact, Forecast, Profile, Report, ReportType, Trip } from './types';

const DEFAULT_URL = process.env.EXPO_PUBLIC_API_URL || 'http://10.0.2.2:8001';

let baseUrl = DEFAULT_URL;
let userToken: string | undefined;

export function setBaseUrl(url: string | null | undefined) {
  baseUrl = (url && url.trim() ? url.trim() : DEFAULT_URL).replace(/\/+$/, '');
}
export function getBaseUrl() {
  return baseUrl;
}
export function setToken(token: string | undefined) {
  userToken = token;
}

/** Network or server problem, with a message that is safe to show. */
export class ApiError extends Error {
  status: number;
  offline: boolean;
  constructor(message: string, status = 0, offline = false) {
    super(message);
    this.status = status;
    this.offline = offline;
  }
}

async function request<T>(path: string, options: { method?: string; body?: unknown; timeoutMs?: number } = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 12000);
  try {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (userToken) headers['X-User-Token'] = userToken;
    const resp = await fetch(baseUrl + path, {
      method: options.method ?? 'GET',
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
    if (!resp.ok) {
      let detail = `Server error (${resp.status})`;
      try {
        const data = await resp.json();
        if (typeof data?.detail === 'string') detail = data.detail;
      } catch {
        // keep the generic message
      }
      throw new ApiError(detail, resp.status);
    }
    return (await resp.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError('No connection to the server.', 0, true);
  } finally {
    clearTimeout(timer);
  }
}

function query(params: Record<string, string | number | undefined>) {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join('&')}` : '';
}

export const api = {
  health: () => request<{ ok: boolean; scenario: string }>('/health', { timeoutMs: 5000 }),

  register: (profile: Profile, contacts: Contact[], expoPushToken?: string | null) =>
    request<{ user_id: number; token: string }>('/users', {
      method: 'POST',
      body: {
        name: profile.name,
        phone: profile.phone,
        language: profile.language,
        boat_type: profile.boat_type,
        home_lat: profile.home_lat,
        home_lon: profile.home_lon,
        home_name: profile.home_name,
        expo_push_token: expoPushToken ?? null,
        contacts: contacts.map((c) => ({ name: c.name, phone: c.phone, relation: c.relation })),
      },
    }),
  updateMe: (patch: Partial<Profile> & { expo_push_token?: string }) =>
    request<unknown>('/users/me', { method: 'PUT', body: patch }),
  listContacts: () => request<Contact[]>('/users/me/contacts'),
  addContact: (c: Contact) => request<Contact>('/users/me/contacts', { method: 'POST', body: c }),
  deleteContact: (id: number) => request<{ ok: boolean }>(`/users/me/contacts/${id}`, { method: 'DELETE' }),

  forecast: (lat: number, lon: number, boat: BoatType, language: string) =>
    request<Forecast>(`/advisor/forecast${query({ lat, lon, boat_type: boat, language, days: 3 })}`),
  ask: (question: string, lat: number, lon: number, boat: BoatType, language: string) =>
    request<Advice>('/advisor/ask', {
      method: 'POST',
      body: { question, lat, lon, boat_type: boat, language },
      timeoutMs: 30000, // the server gives the AI up to 20 s before using the template
    }),

  startTrip: (plannedReturn: string, lat: number, lon: number) =>
    request<Trip>('/trips/start', { method: 'POST', body: { planned_return: plannedReturn, lat, lon } }),
  activeTrip: () => request<{ trip: Trip | null }>('/trips/active'),
  pingTrip: (id: number, lat: number, lon: number) =>
    request<Trip>(`/trips/${id}/ping`, { method: 'POST', body: { lat, lon } }),
  endTrip: (id: number) => request<Trip>(`/trips/${id}/end`, { method: 'POST' }),
  sos: (lat: number, lon: number) => request<unknown>('/trips/sos', { method: 'POST', body: { lat, lon }, timeoutMs: 8000 }),

  reports: (lat: number, lon: number, radiusKm = 25) =>
    request<Report[]>(`/reports${query({ lat, lon, radius_km: radiusKm })}`),
  createReport: (type: ReportType, lat: number, lon: number, note: string, anonymous: boolean) =>
    request<Report>('/reports', { method: 'POST', body: { type, lat, lon, note: note || null, anonymous } }),
  voteReport: (id: number, dir: 'up' | 'down') =>
    request<Report>(`/reports/${id}/vote`, { method: 'POST', body: { dir } }),

  setScenario: (mode: string) => request<{ mode: string }>('/demo/scenario', { method: 'POST', body: { mode } }),
  seed: () => request<unknown>('/demo/seed', { method: 'POST' }),
  fastForward: (tripId: number) => request<unknown>(`/demo/trips/${tripId}/fast-forward`, { method: 'POST' }),
  tick: () => request<{ checked: number; overdue: number; alerts: number }>('/demo/tick', { method: 'POST' }),
};
