import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { translate, type Translate } from '../i18n';
import { ApiError, api, getBaseUrl, setBaseUrl, setFamilyToken, setToken } from './api';
import { registerForPush } from './notifications';
import type { Contact, FamilyLink, Profile, Trip } from './types';

const KEYS = {
  profile: 'seasafe.profile',
  contacts: 'seasafe.contacts',
  apiUrl: 'seasafe.apiUrl',
  trip: 'seasafe.trip',
  family: 'seasafe.family',
};

export async function loadJson<T>(key: string): Promise<T | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export async function saveJson(key: string, value: unknown): Promise<void> {
  try {
    if (value === null || value === undefined) await AsyncStorage.removeItem(key);
    else await AsyncStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage full or unavailable: the app still works for this session
  }
}

type AppState = {
  ready: boolean;
  profile: Profile | null;
  contacts: Contact[];
  trip: Trip | null;
  apiUrl: string;
  t: Translate;
  completeOnboarding: (profile: Profile, contacts: Contact[]) => Promise<boolean>;
  updateProfile: (patch: Partial<Profile>) => Promise<void>;
  addContact: (contact: Contact) => Promise<void>;
  removeContact: (index: number) => Promise<void>;
  setTrip: (trip: Trip | null) => void;
  setApiUrl: (url: string) => Promise<void>;
  ensureRegistered: () => Promise<boolean>;
  /** Set when this phone belongs to a fisher's family member instead of a fisher. */
  family: FamilyLink | null;
  setFamily: (link: FamilyLink | null) => Promise<void>;
  /** The simulation pop-up (weather and event injection). */
  simOpen: boolean;
  setSimOpen: (open: boolean) => void;
};

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [trip, setTripState] = useState<Trip | null>(null);
  const [apiUrl, setApiUrlState] = useState(getBaseUrl());
  const [family, setFamilyState] = useState<FamilyLink | null>(null);
  const [simOpen, setSimOpen] = useState(false);

  // Latest values for callbacks that outlive a render.
  const profileRef = useRef<Profile | null>(null);
  const contactsRef = useRef<Contact[]>([]);
  profileRef.current = profile;
  contactsRef.current = contacts;

  const persistProfile = useCallback(async (next: Profile | null) => {
    profileRef.current = next;
    setProfile(next);
    setToken(next?.token);
    await saveJson(KEYS.profile, next);
  }, []);

  const persistContacts = useCallback(async (next: Contact[]) => {
    contactsRef.current = next;
    setContacts(next);
    await saveJson(KEYS.contacts, next);
  }, []);

  /** Register with the backend if this phone has no token yet (or the server forgot it). */
  const ensureRegistered = useCallback(async (): Promise<boolean> => {
    const current = profileRef.current;
    if (!current) return false;
    try {
      if (current.token) {
        try {
          await api.activeTrip();
          return true;
        } catch (err) {
          if (!(err instanceof ApiError) || err.status !== 401) return false;
          // The server database was reset: fall through and register again.
        }
      }
      const pushToken = await registerForPush();
      const result = await api.register(current, contactsRef.current, pushToken);
      await persistProfile({ ...current, user_id: result.user_id, token: result.token });
      return true;
    } catch {
      return false;
    }
  }, [persistProfile]);

  useEffect(() => {
    (async () => {
      const [savedUrl, savedProfile, savedContacts, savedTrip, savedFamily] = await Promise.all([
        loadJson<string>(KEYS.apiUrl),
        loadJson<Profile>(KEYS.profile),
        loadJson<Contact[]>(KEYS.contacts),
        loadJson<Trip>(KEYS.trip),
        loadJson<FamilyLink>(KEYS.family),
      ]);
      setBaseUrl(savedUrl);
      setApiUrlState(getBaseUrl());
      if (savedFamily) {
        setFamilyToken(savedFamily.token);
        setFamilyState(savedFamily);
      }
      if (savedProfile) {
        profileRef.current = savedProfile;
        setProfile(savedProfile);
        setToken(savedProfile.token);
      }
      if (savedContacts) {
        contactsRef.current = savedContacts;
        setContacts(savedContacts);
      }
      if (savedTrip) setTripState(savedTrip);
      setReady(true);
      if (savedProfile) void ensureRegistered();
    })();
  }, [ensureRegistered]);

  const completeOnboarding = useCallback(
    async (next: Profile, nextContacts: Contact[]) => {
      await persistContacts(nextContacts);
      await persistProfile(next);
      return ensureRegistered();
    },
    [ensureRegistered, persistContacts, persistProfile],
  );

  const updateProfile = useCallback(
    async (patch: Partial<Profile>) => {
      const current = profileRef.current;
      if (!current) return;
      const next = { ...current, ...patch };
      await persistProfile(next);
      if (next.token) {
        const { token: _token, user_id: _id, ...serverFields } = patch;
        try {
          await api.updateMe(serverFields);
        } catch {
          // saved locally; the server copy catches up on the next successful update
        }
      } else {
        void ensureRegistered();
      }
    },
    [ensureRegistered, persistProfile],
  );

  const addContact = useCallback(
    async (contact: Contact) => {
      let saved = contact;
      if (profileRef.current?.token) {
        try {
          saved = { ...contact, id: (await api.addContact(contact)).id };
        } catch {
          // kept on the phone so SOS still reaches this contact
        }
      }
      await persistContacts([...contactsRef.current, saved]);
    },
    [persistContacts],
  );

  const removeContact = useCallback(
    async (index: number) => {
      const target = contactsRef.current[index];
      if (!target) return;
      if (target.id !== undefined && profileRef.current?.token) {
        try {
          await api.deleteContact(target.id);
        } catch {
          // removed locally anyway
        }
      }
      await persistContacts(contactsRef.current.filter((_, i) => i !== index));
    },
    [persistContacts],
  );

  const setTrip = useCallback((next: Trip | null) => {
    setTripState(next);
    void saveJson(KEYS.trip, next);
  }, []);

  const setApiUrl = useCallback(async (url: string) => {
    setBaseUrl(url);
    setApiUrlState(getBaseUrl());
    await saveJson(KEYS.apiUrl, url.trim() || null);
  }, []);

  const setFamily = useCallback(async (link: FamilyLink | null) => {
    setFamilyToken(link?.token);
    setFamilyState(link);
    await saveJson(KEYS.family, link);
  }, []);

  const lang = profile?.language ?? 'en';
  const t = useCallback<Translate>((key, params) => translate(lang, key, params), [lang]);

  const value = useMemo<AppState>(
    () => ({
      ready, profile, contacts, trip, apiUrl, t,
      completeOnboarding, updateProfile, addContact, removeContact, setTrip, setApiUrl, ensureRegistered,
      family, setFamily, simOpen, setSimOpen,
    }),
    [ready, profile, contacts, trip, apiUrl, t, completeOnboarding, updateProfile, addContact, removeContact, setTrip, setApiUrl,
      ensureRegistered, family, setFamily, simOpen],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const value = useContext(Ctx);
  if (!value) throw new Error('useApp must be used inside AppProvider');
  return value;
}
