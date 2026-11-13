export type Level = 'SAFE' | 'CAUTION' | 'UNSAFE';
export type BoatType = 'non_motorised' | 'motorised' | 'mechanised';
export type Lang = 'en' | 'ml';
export type ReportType =
  | 'rough_sea'
  | 'storm'
  | 'harbour_mouth_rough'
  | 'strong_current'
  | 'debris'
  | 'oil_spill'
  | 'boat_in_trouble'
  | 'no_fish';

export type Reason = {
  factor: string;
  value: number | null;
  unit: string;
  threshold: number | null;
  level: Level;
  text_key: string;
  detail: string;
  text: string;
};

export type SafeWindow = {
  start: string;
  end: string;
  return_by: string;
  start_label: string;
  end_label: string;
  return_by_label: string;
  hours: number;
};

export type DaySummary = {
  day_index: number;
  date: string;
  verdict: Level;
  verdict_word: string;
  worst_level: Level;
  safe_hours: number;
  window: SafeWindow | null;
  return_by: string | null;
  confidence: 'high' | 'medium' | 'low';
  reasons: Reason[];
  short_answer: string;
};

export type HourRisk = {
  time: string;
  day_index: number;
  hour: number;
  level: Level;
  is_day: boolean;
  past: boolean;
  wave_height: number | null;
  wave_period: number | null;
  wind_speed: number | null;
  wind_gust: number | null;
  wind_from?: string | null;
  wind_from_deg?: number | null;
  current_speed?: number | null;
  current_to?: string | null;
  current_to_deg?: number | null;
  tide_m?: number | null;
  reasons: Reason[];
};

export type SeaState = {
  wind_speed: number | null;
  wind_gust: number | null;
  wind_from_deg: number | null;
  wind_from: string | null;
  current_speed: number | null;
  current_to_deg: number | null;
  current_to: string | null;
  tide_m: number | null;
  tide_state: 'rising' | 'falling' | 'slack' | null;
  depth_m: number | null;
  wave_height: number | null;
  wave_period: number | null;
  swell_height: number | null;
  home_course: string | null;
  head_wind_home: number | null;
  current_against_home: number | null;
};

export type HarbourMouth = {
  level: Level;
  breaker_m: number | null;
  ebb: boolean;
  long_swell: boolean;
  closes_at: string | null;
  closes_label: string | null;
  days: { day_index: number; date: string; worst_level: Level; windows: { start: string; end: string; hours: number; start_label: string; end_label: string }[] }[];
  hourly: { time: string; day_index: number; hour: number; level: Level; breaker_m: number | null; ebb: boolean; past: boolean }[];
};

export type Buddy = {
  id: number;
  name: string;
  boat_type: BoatType;
  home_name: string;
  status: 'ashore' | 'active' | 'overdue' | 'emergency';
  planned_return: string | null;
  last_ping_at: string | null;
  lat: number | null;
  lon: number | null;
  distance_km: number | null;
};

export type OfficialWarning = {
  id: number;
  title: string;
  message: string;
  source: string;
  expires_at: string;
};

export type Report = {
  id: number;
  type: ReportType;
  lat: number;
  lon: number;
  note: string | null;
  anonymous: boolean;
  reporter: string | null;
  created_at: string;
  expires_at: string;
  life_left: number;
  up: number;
  down: number;
  distance_km: number | null;
  hidden?: boolean;
};

export type Forecast = {
  boat_type: BoatType;
  language: string;
  generated_at: string;
  fetched_at: string;
  stale: boolean;
  age_minutes?: number;
  scenario: string;
  days: DaySummary[];
  hourly: HourRisk[];
  current: HourRisk | null;
  harbour_mouth?: HarbourMouth;
  sea?: SeaState;
  best_days: { date: string; safe_daylight_hours: number; verdict: Level }[];
  warnings: OfficialWarning[];
  reports_nearby: Report[];
  advisory: string;
};

export type Advice = Forecast & {
  question: string;
  day_index: number;
  date: string;
  verdict: Level;
  verdict_word: string;
  window: SafeWindow | null;
  return_by: string | null;
  confidence: 'high' | 'medium' | 'low';
  reasons: Reason[];
  answer: string;
  short_answer: string;
  source: 'ai' | 'template';
};

export type Trip = {
  id: number;
  status: 'active' | 'returned' | 'overdue' | 'emergency';
  started_at: string;
  planned_return: string;
  grace_minutes: number;
  start_lat: number;
  start_lon: number;
  last_lat: number | null;
  last_lon: number | null;
  last_ping_at: string | null;
  /** False while the fisher is still being asked "are you back?" before the family is told. */
  contacts_alerted: boolean;
  forecast_snapshot: HourRisk[];
  head_back: { message: string; created_at: string } | null;
  max_offshore_km?: number;
  auto_sos_sent?: boolean;
  /** When each step happens if there is no word from the fisher. */
  escalation?: {
    ask_at: string;
    contacts_at: string;
    auto_sos_at: string;
    offshore_km: number;
    signal_silent_minutes: number;
  };
};

export type ScheduledTrip = {
  id: number;
  status: 'proposed' | 'scheduled' | 'started' | 'cancelled' | 'expired';
  verdict: Level;
  note: string;
  depart_at: string;
  return_at: string;
  depart_label: string;
  return_label: string;
  day_label: string;
};

export type AssistantAction = 'none' | 'schedule_trip' | 'confirm_schedule' | 'cancel_schedule' | 'sos_help';

export type AssistantReply = {
  reply: string;
  action: AssistantAction;
  proposal: ScheduledTrip | null;
  scheduled: ScheduledTrip[];
  source: 'ai' | 'rules' | 'guard';
  today: { verdict: Level; short_answer: string };
};

export type AssistantTurn = { id: number | string; role: 'user' | 'assistant'; text: string; created_at?: string };

export type ChatMessage = { id: number; channel: string; text: string; author: string; mine: boolean; created_at: string };

export type CommunityEvent = {
  id: number;
  title: string;
  description: string;
  kind: string;
  place_name: string;
  starts_at: string;
  organiser: string | null;
  is_organiser: boolean;
  going_count: number;
  going: boolean;
  distance_km: number | null;
  channel: string;
};

export type Contact = { id?: number; name: string; phone: string; relation: string; link_code?: string | null; family_app?: boolean };

export type FamilyStatus = {
  contact: { name: string; relation: string };
  fisher: { name: string; home_name: string; boat_type: BoatType | '' };
  trip: {
    status: Trip['status'];
    started_at: string;
    planned_return: string;
    ended_at: string | null;
    last_contact_at: string | null;
  } | null;
};

export type FamilyLink = FamilyStatus & { token: string };

export type FamilyMessage = {
  id: number;
  kind: 'overdue' | 'sos' | 'auto_sos' | 'all_clear' | 'extended';
  text: string;
  created_at: string;
  urgent: boolean;
};

export type Profile = {
  name: string;
  phone: string;
  language: Lang;
  boat_type: BoatType;
  home_lat: number;
  home_lon: number;
  home_name: string;
  user_id?: number;
  token?: string;
};
