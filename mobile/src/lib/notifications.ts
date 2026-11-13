import Constants from 'expo-constants';
import { Platform } from 'react-native';

// expo-notifications is loaded lazily and skipped in Expo Go, where remote push
// is not available on Android. Everything here fails soft: the trip screen also
// polls the server, so alerts still show without push.
const inExpoGo = Constants.executionEnvironment === 'storeClient';

let Notifications: typeof import('expo-notifications') | null = null;
let configured = false;

function load(): typeof import('expo-notifications') | null {
  if (inExpoGo || Platform.OS === 'web') return null;
  if (!Notifications) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      Notifications = require('expo-notifications') as typeof import('expo-notifications');
    } catch {
      Notifications = null;
    }
  }
  return Notifications;
}

async function configure(): Promise<typeof import('expo-notifications') | null> {
  const N = load();
  if (!N) return null;
  try {
    if (!configured) {
      N.setNotificationHandler({
        handleNotification: async () => ({
          shouldPlaySound: true,
          shouldSetBadge: false,
          shouldShowBanner: true,
          shouldShowList: true,
        }),
      });
      if (Platform.OS === 'android') {
        await N.setNotificationChannelAsync('alerts', {
          name: 'Sea Safe alerts',
          importance: N.AndroidImportance.MAX,
          vibrationPattern: [0, 400, 200, 400],
        });
      }
      configured = true;
    }
    const current = await N.getPermissionsAsync();
    if (!current.granted) {
      const asked = await N.requestPermissionsAsync();
      if (!asked.granted) return null;
    }
    return N;
  } catch {
    return null;
  }
}

/** Expo push token for this phone, or null when push is not available. */
export async function registerForPush(): Promise<string | null> {
  const N = await configure();
  if (!N) return null;
  try {
    const projectId: string | undefined =
      Constants.expoConfig?.extra?.eas?.projectId ?? (Constants as { easConfig?: { projectId?: string } }).easConfig?.projectId;
    const token = await N.getExpoPushTokenAsync(projectId ? { projectId } : undefined);
    return token.data ?? null;
  } catch {
    return null;
  }
}

/**
 * Queue a notification on the phone for a later time. It fires with no signal and with the
 * app closed, which is what makes "head back" and "are you back?" work out at sea.
 * Returns an id for cancelNotification, or null when it could not be queued.
 */
export async function notifyAt(when: Date, title: string, body: string): Promise<string | null> {
  if (when.getTime() <= Date.now() + 5000) return null;
  const N = await configure();
  if (!N) return null;
  try {
    return await N.scheduleNotificationAsync({
      content: { title, body, sound: true },
      trigger: { type: N.SchedulableTriggerInputTypes.DATE, date: when, channelId: 'alerts' },
    });
  } catch {
    return null;
  }
}

export async function cancelNotification(id: string | null | undefined): Promise<void> {
  if (!id) return;
  const N = load();
  if (!N) return;
  try {
    await N.cancelScheduledNotificationAsync(id);
  } catch {
    // already fired or cancelled
  }
}

/** Show a notification from the app itself (used when the trip poll finds a new alert). */
export async function notifyLocal(title: string, body: string): Promise<void> {
  const N = await configure();
  if (!N) return;
  try {
    await N.scheduleNotificationAsync({ content: { title, body, sound: true }, trigger: null });
  } catch {
    // the in-app banner is still shown
  }
}
