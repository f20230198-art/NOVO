import en, { type StringKey } from './en';
import ml from './ml';
import type { Lang } from '../lib/types';

const tables = { en, ml };

export const LANGUAGES: { code: Lang; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'ml', label: 'മലയാളം' },
];

/** BCP-47 locale for speech recognition and text-to-speech. */
export const speechLocale: Record<Lang, string> = { en: 'en-IN', ml: 'ml-IN' };

export type Translate = (key: StringKey, params?: Record<string, string | number>) => string;

export function translate(lang: Lang, key: StringKey, params?: Record<string, string | number>): string {
  let text: string = (tables[lang] ?? en)[key] ?? en[key] ?? key;
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replace(`{${name}}`, String(value));
    }
  }
  return text;
}

export type { StringKey };
