import type {
  Advice,
  AssistantReply,
  AssistantTurn,
  BoatType,
  Buddy,
  ChatMessage,
  CommunityEvent,
  Contact,
  FamilyLink,
  FamilyMessage,
  FamilyStatus,
  Forecast,
  Profile,
  Report,
  ReportType,
  ScheduledTrip,
  Trip,
} from './types';

const DEFAULT_URL = process.env.EXPO_PUBLIC_API_URL || 'http://10.0.2.2:8001';

let baseUrl = DEFAULT_URL;
let userToken: string | undefined;
let familyToken: string | undefined;

export function setFamilyToken(token: string | undefined) {
  familyToken = token;
}

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
  retryAfter: number;
  constructor(message: string, status = 0, offline = false, retryAfter = 0) {
    super(message);
    this.status = status;
    this.offline = offline;
    this.retryAfter = retryAfter;
  }
}

async function request<T>(path: string, options: { method?: string; body?: unknown; timeoutMs?: number } = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 12000);
  try {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (userToken) headers['X-User-Token'] = userToken;
    if (familyToken) headers['X-Family-Token'] = familyToken;
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
      throw new ApiError(detail, resp.status, false, Number(resp.headers.get('retry-after') ?? 0) || 0);
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
  uploadTrack: (id: number, points: { lat: number; lon: number; at: string }[]) =>
    request<Trip>(`/trips/${id}/track`, { method: 'POST', body: { points } }),
  endTrip: (id: number) => request<Trip>(`/trips/${id}/end`, { method: 'POST' }),
  extendTrip: (id: number, minutes: number) =>
    request<Trip>(`/trips/${id}/extend`, { method: 'POST', body: { minutes } }),
  sos: (lat: number, lon: number, fix: 'gps' | 'last_known' | 'home' = 'gps') =>
    request<unknown>('/trips/sos', { method: 'POST', body: { lat, lon, fix }, timeoutMs: 8000 }),

  buddies: () => request<Buddy[]>('/buddies'),
  addBuddy: (phone: string) => request<Buddy>('/buddies', { method: 'POST', body: { phone } }),
  removeBuddy: (id: number) => request<{ ok: boolean }>(`/buddies/${id}`, { method: 'DELETE' }),

  reports: (lat: number, lon: number, radiusKm = 25) =>
    request<Report[]>(`/reports${query({ lat, lon, radius_km: radiusKm })}`),
  createReport: (type: ReportType, lat: number, lon: number, note: string, anonymous: boolean) =>
    request<Report>('/reports', { method: 'POST', body: { type, lat, lon, note: note || null, anonymous } }),
  voteReport: (id: number, dir: 'up' | 'down') =>
    request<Report>(`/reports/${id}/vote`, { method: 'POST', body: { dir } }),

  assistantChat: (message: string, language?: string) =>
    request<AssistantReply>('/assistant/chat', { method: 'POST', body: { message, language }, timeoutMs: 30000 }),
  assistantHistory: () => request<AssistantTurn[]>('/assistant/history'),
  clearAssistantHistory: () => request<{ ok: boolean }>('/assistant/history', { method: 'DELETE' }),

  scheduled: () => request<ScheduledTrip[]>('/schedule'),
  confirmScheduled: (id: number) => request<ScheduledTrip>(`/schedule/${id}/confirm`, { method: 'POST' }),
  cancelScheduled: (id: number) => request<ScheduledTrip>(`/schedule/${id}/cancel`, { method: 'POST' }),
  startScheduled: (id: number, lat: number, lon: number) =>
    request<Trip>(`/schedule/${id}/start`, { method: 'POST', body: { lat, lon } }),

  messages: (channel: string, afterId = 0) =>
    request<ChatMessage[]>(`/community/messages${query({ channel, after_id: afterId })}`),
  postMessage: (channel: string, text: string) =>
    request<ChatMessage>(`/community/messages${query({ channel })}`, { method: 'POST', body: { text } }),
  flagMessage: (id: number) => request<{ ok: boolean; hidden: boolean }>(`/community/messages/${id}/flag`, { method: 'POST' }),
  events: () => request<CommunityEvent[]>('/community/events'),
  createEvent: (e: { title: string; description: string; kind: string; place_name: string; starts_at: string }) =>
    request<CommunityEvent>('/community/events', { method: 'POST', body: e }),
  rsvp: (id: number, going: boolean) =>
    request<CommunityEvent>(`/community/events/${id}/rsvp`, { method: 'POST', body: { going } }),

  familyLink: (code: string, expoPushToken?: string | null) =>
    request<FamilyLink>('/family/link', { method: 'POST', body: { code, expo_push_token: expoPushToken ?? null } }),
  familyMe: () => request<FamilyStatus>('/family/me'),
  familyMessages: (afterId = 0) => request<FamilyMessage[]>(`/family/messages${query({ after_id: afterId })}`),
  familyUnlink: () => request<{ ok: boolean }>('/family/me', { method: 'DELETE' }),

  setScenario: (mode: string, lat?: number, lon?: number) =>
    request<{ mode: string; warning_id: number | null }>('/demo/scenario', { method: 'POST', body: { mode, lat, lon } }),
  injectWarning: (kind: string, lat: number, lon: number) =>
    request<unknown>('/demo/inject/warning', { method: 'POST', body: { kind, lat, lon } }),
  injectReport: (type: ReportType, lat: number, lon: number) =>
    request<unknown>('/demo/inject/report', { method: 'POST', body: { type, lat, lon } }),
  clearInjections: () => request<{ mode: string; removed: number }>('/demo/inject/clear', { method: 'POST' }),
  seed: () => request<unknown>('/demo/seed', { method: 'POST' }),
  fastForward: (tripId: number) => request<unknown>(`/demo/trips/${tripId}/fast-forward`, { method: 'POST' }),
  loseSignal: (tripId: number) => request<unknown>(`/demo/trips/${tripId}/lose-signal`, { method: 'POST' }),
  tick: () => request<{ checked: number; overdue: number; alerts: number }>('/demo/tick', { method: 'POST' }),
};
