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

export function speak(text: string, lang: Lang): void {
  try {
    Speech.stop();
    Speech.speak(text, { language: speechLocale[lang], rate: 0.95 });
  } catch {
    // no TTS voice installed: the text is on screen
  }
}

export function stopSpeaking(): void {
  try {
    Speech.stop();
  } catch {
    // nothing to stop
  }
}
