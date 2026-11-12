import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, Vibration, View } from 'react-native';

import { HourStrip, LevelPill, ReasonList } from '../../components/forecast';
import { Banner, BigButton, Card, Screen, SectionTitle } from '../../components/ui';
import { api } from '../../lib/api';
import { formatClock, formatDuration, num } from '../../lib/format';
import { getWorkingPosition } from '../../lib/location';
import { notifyLocal } from '../../lib/notifications';
import { loadJson, useApp } from '../../lib/store';
import { colors } from '../../lib/theme';
import type { Forecast, HourRisk, Trip } from '../../lib/types';

const HALF_HOUR = 30 * 60 * 1000;
const FIVE_MIN = 5 * 60 * 1000;

function roundUpToHalfHour(ms: number): Date {
  return new Date(Math.ceil(ms / HALF_HOUR) * HALF_HOUR);
}

/** The saved-forecast hour that covers `now`, for when there is no signal. */
function snapshotHour(trip: Trip, now: number): HourRisk | null {
  return (
    trip.forecast_snapshot.find((h) => {
      const start = new Date(h.time).getTime();
      return start <= now && now < start + 60 * 60 * 1000;
    }) ?? null
  );
}

export default function TripScreen() {
  const { profile, trip, setTrip, t, ensureRegistered } = useApp();
  const router = useRouter();
  const params = useLocalSearchParams<{ returnBy?: string }>();

  const [now, setNow] = useState(Date.now());
  const [returnAt, setReturnAt] = useState<Date>(() => roundUpToHalfHour(Date.now() + 4 * 60 * 60 * 1000));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; tone: 'info' | 'warn' } | null>(null);
  const [conditions, setConditions] = useState<HourRisk | null>(null);
  const [conditionsLive, setConditionsLive] = useState(false);

  const lastHeadBack = useRef<string | null>(null);
  const lastStatus = useRef<string | null>(null);
  const tripRef = useRef<Trip | null>(trip);
  tripRef.current = trip;

  const tripId = trip?.id;
  const isOpen = Boolean(trip && trip.status !== 'returned');

  // Clock for the countdown.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 10000);
    return () => clearInterval(id);
  }, []);

  // Default return time: the advisor's return-by (passed from Home), else today's window, else +4 h.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const fromAdvice = params.returnBy ? new Date(params.returnBy) : null;
      if (fromAdvice && fromAdvice.getTime() > Date.now()) {
        setReturnAt(fromAdvice);
        return;
      }
      const cached = await loadJson<{ forecast: Forecast }>('seasafe.forecast');
      const todayReturn = cached?.forecast.days[0]?.return_by;
      if (!cancelled && todayReturn && new Date(todayReturn).getTime() > Date.now()) setReturnAt(new Date(todayReturn));
    })();
    return () => {
      cancelled = true;
    };
  }, [params.returnBy]);

  const applyServerTrip = useCallback(
    (next: Trip | null) => {
      // Alert once per head-back message: skip one this phone has already shown.
      const seen = lastHeadBack.current ?? tripRef.current?.head_back?.created_at ?? null;
      if (next?.head_back && next.head_back.created_at !== seen) {
        Vibration.vibrate([0, 500, 200, 500]);
        void notifyLocal(t('headBack'), next.head_back.message);
      }
      lastHeadBack.current = next?.head_back?.created_at ?? lastHeadBack.current;
      if (next && next.status === 'overdue' && lastStatus.current === 'active') {
        void notifyLocal(t('tripOverdue'), t('familyAlerted'));
      }
      lastStatus.current = next?.status ?? null;
      setTrip(next);
    },
    [setTrip, t],
  );

  const refreshTrip = useCallback(async () => {
    if (!profile?.token) return;
    try {
      applyServerTrip((await api.activeTrip()).trip);
    } catch {
      // offline: keep showing the trip saved on the phone
    }
  }, [applyServerTrip, profile?.token]);

  useFocusEffect(
    useCallback(() => {
      void refreshTrip();
    }, [refreshTrip]),
  );

  // While a trip is open: poll its status (head-back / overdue arrive this way without push).
  useEffect(() => {
    if (!isOpen) return;
    const id = setInterval(refreshTrip, 20000);
    return () => clearInterval(id);
  }, [isOpen, refreshTrip]);

  // While a trip is open: every 5 minutes send the position and refresh the sea conditions.
  useEffect(() => {
    if (!isOpen || tripId === undefined || !profile) return;
    let cancelled = false;
    const update = async () => {
      const current = tripRef.current;
      if (!current) return;
      const position = await getWorkingPosition({ lat: profile.home_lat, lon: profile.home_lon });
      api.pingTrip(current.id, position.lat, position.lon).catch(() => {});
      try {
        const fc = await api.forecast(position.lat, position.lon, profile.boat_type, profile.language);
        if (!cancelled) {
          setConditions(fc.current);
          setConditionsLive(true);
        }
      } catch {
        if (!cancelled) {
          setConditions(snapshotHour(current, Date.now()));
          setConditionsLive(false);
        }
      }
    };
    void update();
    const id = setInterval(update, FIVE_MIN);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [isOpen, tripId, profile]);

  const start = async () => {
    if (!profile) return;
    if (returnAt.getTime() <= Date.now()) {
      setMessage({ text: t('returnInPast'), tone: 'warn' });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      if (!profile.token && !(await ensureRegistered())) throw new Error('offline');
      const position = await getWorkingPosition({ lat: profile.home_lat, lon: profile.home_lon });
      const started = await api.startTrip(returnAt.toISOString(), position.lat, position.lon);
      lastHeadBack.current = null;
      lastStatus.current = started.status;
      setTrip(started);
    } catch {
      setMessage({ text: t('tripNeedsServer'), tone: 'warn' });
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    if (!trip) return;
    setBusy(true);
    try {
      await api.endTrip(trip.id);
      setTrip(null);
      setConditions(null);
      setMessage({ text: t('welcomeBack'), tone: 'info' });
    } catch {
      // Keep the trip open: closing it only on the phone would still alert the family.
      setMessage({ text: t('noConnection'), tone: 'warn' });
    } finally {
      setBusy(false);
    }
  };

  if (!profile) return null;

  if (!trip || !isOpen) {
    return (
      <Screen title={t('tabTrip')}>
        {message ? <Banner text={message.text} tone={message.tone} icon={message.tone === 'warn' ? '⚠' : '✔'} /> : null}
        <Card>
          <SectionTitle>{t('planTrip')}</SectionTitle>
          <Text style={styles.label}>{t('returnTime')}</Text>
          <Text style={styles.bigTime} accessibilityLabel={`${t('returnTime')} ${formatClock(returnAt)}`}>
            {formatClock(returnAt)}
          </Text>
          <Text style={styles.sub}>{returnAt.toDateString()}</Text>
          <View style={styles.row}>
            <BigButton
              label={t('earlier')}
              onPress={() => setReturnAt(new Date(returnAt.getTime() - HALF_HOUR))}
              color={colors.line}
              textColor={colors.ink}
              style={styles.flex}
            />
            <BigButton
              label={t('later')}
              onPress={() => setReturnAt(new Date(returnAt.getTime() + HALF_HOUR))}
              color={colors.line}
              textColor={colors.ink}
              style={styles.flex}
            />
          </View>
          <Text style={styles.sub}>{t('graceNote', { n: 30 })}</Text>
        </Card>
        <BigButton label={busy ? t('starting') : t('startTrip')} icon="⛵" onPress={start} busy={busy} color={colors.safe} style={styles.tall} />
      </Screen>
    );
  }

  const plannedMs = new Date(trip.planned_return).getTime();
  const remaining = plannedMs - now;
  const late = remaining < 0;
  const statusColor = trip.status === 'active' && !late ? colors.sea : colors.unsafe;
  const statusText =
    trip.status === 'emergency' ? t('tripEmergency') : trip.status === 'overdue' || late ? t('tripOverdue') : t('tripActive');

  return (
    <Screen title={t('tabTrip')}>
      {message ? <Banner text={message.text} tone={message.tone} icon="⚠" /> : null}
      {trip.head_back ? <Banner tone="danger" icon="🚨" text={trip.head_back.message} /> : null}

      <View style={[styles.status, { backgroundColor: statusColor }]}>
        <Text style={styles.statusText}>
          {trip.status === 'active' && !late ? '⛵' : '🚨'} {statusText}
        </Text>
        <Text style={styles.statusLabel}>{late ? t('overdueBy') : t('timeLeft')}</Text>
        <Text style={styles.countdown}>{formatDuration(remaining)}</Text>
        <Text style={styles.statusLabel}>
          ↩ {t('returnBy')} {formatClock(new Date(plannedMs))}
        </Text>
        {trip.status === 'overdue' || trip.status === 'emergency' ? (
          <Text style={styles.statusLabel}>{t('familyAlerted')}</Text>
        ) : (
          <Text style={styles.statusLabel}>{t('graceNote', { n: trip.grace_minutes })}</Text>
        )}
      </View>

      <BigButton label={t('imBack')} icon="🏠" onPress={finish} busy={busy} color={colors.safe} style={styles.tall} />

      <Card>
        <View style={styles.rowBetween}>
          <SectionTitle>{t('conditionsNow')}</SectionTitle>
          {conditions ? <LevelPill level={conditions.level} /> : null}
        </View>
        {conditions ? (
          <>
            <Text style={styles.numbers}>
              🌊 {num(conditions.wave_height)} m   💨 {num(conditions.wind_speed, 0)} km/h   {t('gusts')} {num(conditions.wind_gust, 0)} km/h
            </Text>
            <ReasonList reasons={conditions.reasons} />
            {!conditionsLive ? <Text style={styles.sub}>📴 {t('savedForecast')}</Text> : null}
          </>
        ) : (
          <Text style={styles.sub}>{t('loading')}</Text>
        )}
      </Card>

      {trip.forecast_snapshot.length > 0 ? (
        <Card>
          <SectionTitle>{t('savedForecast')}</SectionTitle>
          <HourStrip hours={trip.forecast_snapshot} selected={null} onSelect={() => {}} />
        </Card>
      ) : null}

      <BigButton
        label={t('reportHazard')}
        icon="⚠️"
        onPress={() => router.push({ pathname: '/watch', params: { report: '1' } })}
        color={colors.caution}
        textColor={colors.ink}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  row: { flexDirection: 'row', gap: 10, marginVertical: 10 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  label: { fontSize: 16, fontWeight: '700', color: colors.inkSoft },
  bigTime: { fontSize: 56, fontWeight: '900', color: colors.ink },
  sub: { fontSize: 14, color: colors.inkSoft, lineHeight: 20 },
  tall: { minHeight: 84 },
  status: { borderRadius: 20, padding: 18, alignItems: 'center', gap: 2 },
  statusText: { fontSize: 22, fontWeight: '900', color: colors.white },
  statusLabel: { fontSize: 15, fontWeight: '700', color: colors.white, textAlign: 'center' },
  countdown: { fontSize: 52, fontWeight: '900', color: colors.white },
  numbers: { fontSize: 17, fontWeight: '700', color: colors.ink, marginBottom: 8 },
});
