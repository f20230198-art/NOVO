import { requireOptionalNativeModule } from 'expo-modules-core';
import * as Speech from 'expo-speech';
import { Platform } from 'react-native';

import { speechLocale } from '../i18n';
import type { Lang } from './types';

// expo-speech-recognition has native code that is not in Expo Go. Load it lazily
// so the app still runs there; the Ask box then falls back to typed questions.
type SttModule = typeof import('expo-speech-recognition').ExpoSpeechRecognitionModule;
let stt: SttModule | null | undefined;

function loadStt(): SttModule | null {
  if (stt === undefined) {
    // Probe without throwing first. In dev, a module that throws while loading is
    // reported by LogBox as an uncaught error even when the require is wrapped in try.
    if (!requireOptionalNativeModule('ExpoSpeechRecognition')) {
      stt = null;
      return stt;
    }
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      stt = (require('expo-speech-recognition') as typeof import('expo-speech-recognition')).ExpoSpeechRecognitionModule;
    } catch {
      stt = null;
    }
  }
  return stt;
}

export function voiceInputAvailable(): boolean {
  const mod = loadStt();
  if (!mod) return false;
  try {
    return mod.isRecognitionAvailable();
  } catch {
    return false;
  }
}

// The Google app's recogniser understands Malayalam. A phone's default recogniser may be an
// on-device one that only knows a few major languages, so ask for Google's when it is there.
const GOOGLE_RECOGNISER = 'com.google.android.googlequicksearchbox';

function recogniserPackage(mod: SttModule): string | undefined {
  if (Platform.OS !== 'android') return undefined;
  try {
    return mod.getSpeechRecognitionServices().includes(GOOGLE_RECOGNISER) ? GOOGLE_RECOGNISER : undefined;
  } catch {
    return undefined;
  }
}

/**
 * False only when the phone lists its voices and none of them speaks this language.
 * An empty list means "not known yet", which is treated as fine.
 */
export async function canSpeak(lang: Lang): Promise<boolean> {
  try {
    const voices = await Speech.getAvailableVoicesAsync();
    if (!voices.length) return true;
    const prefix = speechLocale[lang].slice(0, 2).toLowerCase();
    return voices.some((v) => (v.language ?? '').toLowerCase().startsWith(prefix));
  } catch {
    return true;
  }
}

export type ListenHandlers = {
  onText: (text: string, isFinal: boolean) => void;
  onEnd: () => void;
  onError: (code: string) => void;
};

/** Start listening. Returns a stop function, or null when voice input cannot start. */
export async function startListening(lang: Lang, handlers: ListenHandlers): Promise<(() => void) | null> {
  const mod = loadStt();
  if (!mod) return null;
  try {
    const perm = await mod.requestPermissionsAsync();
    if (!perm.granted) {
      handlers.onError('not-allowed');
      return null;
    }
    const subs = [
      mod.addListener('result', (event) => {
        const text = event.results?.[0]?.transcript ?? '';
        if (text) handlers.onText(text, Boolean(event.isFinal));
      }),
      mod.addListener('error', (event) => handlers.onError(String(event.error ?? 'error'))),
      mod.addListener('end', () => {
        subs.forEach((s) => s.remove());
        handlers.onEnd();
      }),
    ];
    mod.start({
      lang: speechLocale[lang],
      interimResults: true,
      continuous: false,
      maxAlternatives: 1,
      androidRecognitionServicePackage: recogniserPackage(mod),
    });
    return () => {
      try {
        mod.stop();
      } catch {
        // already stopped
      }
    };
  } catch {
    handlers.onError('start-failed');
    return null;
  }
}

// ---- the assistant's voice -------------------------------------------------------
//
// Android and iOS do not say which voices are female, so we rank by name. Google's Android
// voices are named like "en-in-x-ahp-network": the 3-letter code is the speaker, "-network"
// voices are the natural-sounding neural ones (they need data; "-local" works offline).

const FEMALE_HINTS = [
  // Google TTS (Android) female speakers
  'en-in-x-ahp', 'en-in-x-cxx', 'en-us-x-sfg', 'en-us-x-tpf', 'en-us-x-tpc', 'en-us-x-iob', 'en-us-x-iog',
  'en-gb-x-gba', 'en-gb-x-gbc', 'en-gb-x-gbg', 'en-au-x-afa', 'en-au-x-aua',
  // Samsung / iOS / generic names
  'female', 'woman', 'veena', 'isha', 'samantha', 'karen', 'moira', 'tessa', 'serena', 'kate', 'fiona', 'ava', 'allison', 'susan', 'zira',
];
const MALE_HINTS = [
  'en-in-x-ene', 'en-in-x-end', 'en-us-x-iol', 'en-us-x-iom', 'en-us-x-tpd', 'en-gb-x-gbb', 'en-gb-x-gbd', 'en-gb-x-rjs',
  'en-au-x-aub', 'en-au-x-aud', 'male', 'rishi', 'daniel', 'alex', 'fred', 'aaron', 'arthur', 'gordon', 'david', 'mark',
];

export function scoreVoice(v: Speech.Voice): number {
  const id = `${v.identifier} ${v.name}`.toLowerCase();
  const language = (v.language ?? '').toLowerCase().replace('_', '-');
  if (!language.startsWith('en')) return -1;
  let score = 0;
  if (language === 'en-in') score += 40;
  else if (language === 'en-gb' || language === 'en-us' || language === 'en-au') score += 20;
  else score += 10;
  if (MALE_HINTS.some((h) => id.includes(h)) && !id.includes('female')) score -= 50;
  else if (FEMALE_HINTS.some((h) => id.includes(h))) score += 30;
  if (id.includes('network') || v.quality === Speech.VoiceQuality.Enhanced) score += 15;
  if (id.includes('notinstalled') || id.includes('not-installed')) score -= 100;
  return score;
}

let chosenVoice: string | null | undefined;

/** The best English, preferably Indian-English, female voice on this phone. Cached. */
export async function assistantVoice(): Promise<string | null> {
  if (chosenVoice !== undefined) return chosenVoice;
  try {
    const voices = await Speech.getAvailableVoicesAsync();
    if (!voices.length) return null; // the TTS engine may not be ready yet; try again next time
    const best = voices.map((v) => ({ v, s: scoreVoice(v) })).filter((x) => x.s >= 0).sort((a, b) => b.s - a.s)[0];
    chosenVoice = best ? best.v.identifier : null;
  } catch {
    chosenVoice = null;
  }
  return chosenVoice;
}

/** "It's calm. Waves about 1.2 metres, wind 20." -> one chunk per sentence, so it breathes. */
export function sentences(text: string): string[] {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (!clean) return [];
  // Split after . ! ? but not inside numbers like 1.2 or times like 10.30.
  const parts = clean.split(/(?<=[.!?])\s+(?=[A-Z0-9"'(])/);
  // Very long sentences also get a breath at a comma.
  return parts.flatMap((p) => (p.length > 160 ? p.split(/(?<=,)\s+/) : [p])).filter(Boolean);
}

const PAUSE_MS = 220; // between sentences
const PITCH = 1.08; // a touch brighter than the engine default
const RATE = 0.92; // a little slower: outdoors, over wind and engine noise
let generation = 0;

export type SpeakHandlers = { onStart?: () => void; onDone?: () => void };

/** Speak a reply sentence by sentence in the assistant's voice. Stops anything already speaking. */
export function speak(text: string, lang: Lang, handlers: SpeakHandlers = {}): void {
  const mine = ++generation;
  try {
    Speech.stop();
  } catch {
    // nothing to stop
  }
  const chunks = sentences(text);
  if (!chunks.length) return;
  void (async () => {
    const voice = lang === 'en' ? await assistantVoice() : null;
    if (mine !== generation) return;
    handlers.onStart?.();
    const say = (i: number) => {
      if (mine !== generation) return;
      if (i >= chunks.length) {
        handlers.onDone?.();
        return;
      }
      const next = (): void => {
        setTimeout(() => say(i + 1), PAUSE_MS);
      };
      // A question rises a little at the end; the engine does this better with a slightly higher pitch.
      const pitch = chunks[i].endsWith('?') ? PITCH + 0.04 : PITCH;
      try {
        Speech.speak(chunks[i], {
          language: speechLocale[lang],
          ...(voice ? { voice } : {}),
          pitch,
          rate: RATE,
          onDone: next,
          onError: next,
        });
      } catch {
        // no TTS voice installed: the text is on screen
        handlers.onDone?.();
      }
    };
    say(0);
  })();
}

export function stopSpeaking(): void {
  generation++;
  try {
    Speech.stop();
  } catch {
    // nothing to stop
  }
}
