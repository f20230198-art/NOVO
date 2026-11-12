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
  reasons: Reason[];
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
  scenario: string;
  days: DaySummary[];
  hourly: HourRisk[];
  current: HourRisk | null;
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
  forecast_snapshot: HourRisk[];
  head_back: { message: string; created_at: string } | null;
};

export type Contact = { id?: number; name: string; phone: string; relation: string };

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
