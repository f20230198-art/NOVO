import type { BoatType, Level, ReportType } from './types';

export const colors = {
  safe: '#1B998B',
  caution: '#F4A261',
  unsafe: '#E63946',
  ink: '#0B2545',
  inkSoft: '#3D5A80',
  bg: '#EEF3F8',
  card: '#FFFFFF',
  line: '#C9D6E2',
  white: '#FFFFFF',
  sea: '#13315C',
};

export const levelColor: Record<Level, string> = {
  SAFE: colors.safe,
  CAUTION: colors.caution,
  UNSAFE: colors.unsafe,
};

/** Text colour that stays readable on each level colour in bright sunlight. */
export const levelInk: Record<Level, string> = {
  SAFE: colors.white,
  CAUTION: colors.ink,
  UNSAFE: colors.white,
};

/** Shape as well as colour, so the level reads without colour vision. */
export const levelIcon: Record<Level, string> = { SAFE: '✔', CAUTION: '⚠', UNSAFE: '✖' };

export const boatIcon: Record<BoatType, string> = {
  non_motorised: '🛶',
  motorised: '🚤',
  mechanised: '🚢',
};

export const reportIcon: Record<ReportType, string> = {
  rough_sea: '🌊',
  storm: '⛈️',
  harbour_mouth_rough: '⚓',
  strong_current: '🌀',
  debris: '🪵',
  oil_spill: '🛢️',
  boat_in_trouble: '🆘',
  no_fish: '🐟',
};

export const REPORT_TYPES = Object.keys(reportIcon) as ReportType[];
export const BOAT_TYPES: BoatType[] = ['non_motorised', 'motorised', 'mechanised'];

export const TOUCH = 56; // minimum touch target, dp

export const HARBOURS = [
  { name: 'Muthalapozhi', lat: 8.635, lon: 76.775 },
  { name: 'Vizhinjam', lat: 8.375, lon: 76.985 },
  { name: 'Kochi', lat: 9.965, lon: 76.235 },
  { name: 'Fujairah', lat: 25.13, lon: 56.36 },
];
