import { Platform } from 'react-native';

import type { BoatType, Level, ReportType } from './types';

/**
 * Sea Safe looks like the things on a Kerala landing beach: sailcloth, boat paint and the
 * storm-signal board at the harbour. Flat paint colours, dark ink, no gloss.
 */
export const colors = {
  // Signal colours. White text passes 4.5:1 on safe and unsafe; caution carries dark ink.
  safe: '#0A7A55',
  caution: '#F0AE12',
  unsafe: '#C8281E',
  ink: '#14212B',
  inkSoft: '#4A5A66',
  bg: '#F3EDE0', // sailcloth
  card: '#FFFDF7',
  line: '#D8CDB6',
  white: '#FFFFFF',
  sea: '#123E7C', // hull blue: primary actions
  seaDeep: '#0B2A57',
  sand: '#E7DCC4',
  rope: '#B08D57',
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

/**
 * Display face: the condensed cut that ships with Android, set heavy, like painted
 * lettering on a hull. Malayalam falls back to the system Malayalam face.
 */
export const display = Platform.select({ android: { fontFamily: 'sans-serif-condensed' }, default: {} }) as {
  fontFamily?: string;
};

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
