import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, Vibration, View } from 'react-native';

import { HourStrip, LevelPill, ReasonList } from '../../components/forecast';
import { BuddyBoats } from '../../components/buddies';
import { Banner, BigButton, Card, Screen, SectionTitle } from '../../components/ui';
import { api } from '../../lib/api';
import { along, bearing, formatClock, formatDuration, num } from '../../lib/format';
import type { Translate } from '../../i18n';
import { getWorkingPosition } from '../../lib/location';
import { cancelNotification, notifyAt, notifyLocal } from '../../lib/notifications';
import { loadJson, saveJson, useApp } from '../../lib/store';
import { clearTrack, sendPosition } from '../../lib/trackQueue';
import { colors } from '../../lib/theme';
import type { Forecast, HourRisk, ScheduledTrip, Trip } from '../../lib/types';

const HALF_HOUR = 30 * 60 * 1000;
const FIVE_MIN = 5 * 60 * 1000;
const HOUR = 60 * 60 * 1000;
const ALARMS_KEY = 'seasafe.tripAlarms';

/** The next hour in the saved forecast that is UNSAFE for this boat, if any. */
function nextUnsafeHour(trip: Trip, now: number): HourRisk | null {
  return trip.forecast_snapshot.find((h) => h.level === 'UNSAFE' && new Date(h.time).getTime() + HOUR > now) ?? null;
}

async function clearAlarms(): Promise<void> {
  const ids = (await loadJson<string[]>(ALARMS_KEY)) ?? [];
  await Promise.all(ids.map((id) => cancelNotification(id)));
  await saveJson(ALARMS_KEY, null);
}

/**
 * Alarms kept on the phone itself, so they ring with no signal and with the app closed:
 * "are you back?" at the return time, and "head back" an hour before the saved forecast
 * turns UNSAFE. The server sends the same alerts when it can reach the phone.
 */
async function setAlarms(trip: Trip, t: Translate): Promise<void> {
  await clearAlarms();
  const ids: string[] = [];
  const back = await notifyAt(new Date(trip.planned_return), t('areYouBack'), t('areYouBackBody'));
  if (back) ids.push(back);
  const bad = nextUnsafeHour(trip, Date.now());
  if (bad) {
    const starts = new Date(bad.time);
    const id = await notifyAt(new Date(starts.getTime() - HOUR), t('headBack'), t('headBackSaved', { time: formatClock(starts) }));
    if (id) ids.push(id);
  }
  await saveJson(ALARMS_KEY, ids);
}

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
  const [scheduled, setScheduled] = useState<ScheduledTrip[]>([]);

  const lastHeadBack = useRef<string | null>(null);
  const lastStatus = useRef<string | null>(null);
  const warnedOffline = useRef<string | null>(null);
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
        void notifyLocal(t('areYouBack'), next.contacts_alerted ? t('familyAlerted') : t('areYouBackBody'));
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
    try {
      setScheduled((await api.scheduled()).filter((s) => s.status === 'scheduled'));
    } catch {
      // offline
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
      void sendPosition(current, position); // queued on the phone when there is no signal
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
      warnedOffline.current = null;
      setTrip(started);
      void setAlarms(started, t);
    } catch {
      setMessage({ text: t('tripNeedsServer'), tone: 'warn' });
    } finally {
      setBusy(false);
    }
  };

  const startFromSchedule = async (s: ScheduledTrip) => {
    if (!profile) return;
    setBusy(true);
    setMessage(null);
    try {
      const position = await getWorkingPosition({ lat: profile.home_lat, lon: profile.home_lon });
      const started = await api.startScheduled(s.id, position.lat, position.lon);
      lastHeadBack.current = null;
      lastStatus.current = started.status;
      warnedOffline.current = null;
      setTrip(started);
      setScheduled((prev) => prev.filter((x) => x.id !== s.id));
      void setAlarms(started, t);
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
      void clearAlarms();
      void clearTrack();
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

  /** "More time": answers the "are you back?" check and moves the return time. */
  const moreTime = async () => {
    if (!trip) return;
    setBusy(true);
    try {
      const updated = await api.extendTrip(trip.id, 30);
      lastStatus.current = updated.status;
      setTrip(updated);
      setMessage(null);
      void setAlarms(updated, t);
    } catch {
      setMessage({ text: t('noConnection'), tone: 'warn' });
    } finally {
      setBusy(false);
    }
  };

  // Out of signal: raise "head back" from the forecast saved on the phone.
  const dangerAhead = trip && isOpen && !trip.head_back ? nextUnsafeHour(trip, now) : null;
  const dangerSoon = dangerAhead && new Date(dangerAhead.time).getTime() - now < 2 * HOUR ? dangerAhead : null;
  const dangerTime = dangerSoon?.time ?? null;
  useEffect(() => {
    if (!dangerTime || warnedOffline.current === dangerTime) return;
    warnedOffline.current = dangerTime;
    Vibration.vibrate([0, 500, 200, 500]);
  }, [dangerTime]);

  if (!profile) return null;

  if (!trip || !isOpen) {
    return (
      <Screen title={t('tabTrip')}>
        {message ? <Banner text={message.text} tone={message.tone} icon={message.tone === 'warn' ? '⚠' : '✔'} /> : null}
        {scheduled.length > 0 ? (
          <Card>
            <SectionTitle>{t('scheduledTrips')}</SectionTitle>
            {scheduled.map((s) => (
              <View key={s.id} style={styles.scheduled}>
                <View style={styles.rowBetween}>
                  <Text style={styles.scheduledWhen}>
                    {s.day_label} · {s.depart_label} → {s.return_label}
                  </Text>
                  <LevelPill level={s.verdict} />
                </View>
                {s.note ? <Text style={styles.sub}>{s.note}</Text> : null}
                <BigButton label={t('startScheduled')} icon="⛵" onPress={() => startFromSchedule(s)} busy={busy} color={colors.safe} />
              </View>
            ))}
          </Card>
        ) : null}
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
        <Card>
          <BuddyBoats />
        </Card>
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
      {dangerSoon ? (
        <Banner tone="danger" icon="🚨" text={`${t('headBack')}: ${t('headBackSaved', { time: formatClock(new Date(dangerSoon.time)) })}`} />
      ) : null}

      <View style={[styles.status, { backgroundColor: statusColor }]}>
        <Text style={styles.statusText}>
          {statusText}
        </Text>
        <Text style={styles.statusLabel}>{late ? t('overdueBy') : t('timeLeft')}</Text>
        <Text style={styles.countdown}>{formatDuration(remaining)}</Text>
        <Text style={styles.statusLabel}>
          {t('returnBy')} {formatClock(new Date(plannedMs))}
        </Text>
        {trip.status === 'emergency' || (trip.status === 'overdue' && trip.contacts_alerted) ? (
          <Text style={styles.statusLabel}>{t('familyAlerted')}</Text>
        ) : trip.status === 'overdue' || late ? (
          <Text style={styles.statusLabel}>{t('areYouBackBody')}</Text>
        ) : (
          <Text style={styles.statusLabel}>{t('graceNote', { n: trip.grace_minutes })}</Text>
        )}
      </View>

      {trip.auto_sos_sent ? <Banner tone="danger" icon="🆘" text={t('autoSosSent')} /> : null}

      <BigButton label={t('imBack')} icon="🏠" onPress={finish} busy={busy} color={colors.safe} style={styles.tall} />
      {trip.status !== 'emergency' ? (
        <BigButton label={t('moreTime')} icon="⏱" onPress={moreTime} busy={busy} color={colors.line} textColor={colors.ink} />
      ) : null}

      {trip.escalation && trip.status !== 'emergency' ? (
        <Card>
          <SectionTitle>{t('ifNoWord')}</SectionTitle>
          {[
            { at: trip.escalation.ask_at, label: t('stepAsk'), icon: '❓' },
            { at: trip.escalation.contacts_at, label: t('stepContacts'), icon: '📩' },
            { at: trip.escalation.auto_sos_at, label: t('stepAutoSos', { km: trip.escalation.offshore_km }), icon: '🆘' },
          ].map((step) => {
            const passed = new Date(step.at).getTime() <= now;
            return (
              <View key={step.icon} style={[styles.step, passed && styles.stepPassed]}>
                <Text style={styles.stepTime}>{formatClock(new Date(step.at))}</Text>
                <Text style={styles.stepLabel}>
                  {step.icon} {step.label}
                </Text>
              </View>
            );
          })}
          <Text style={styles.sub}>
            {t('furthestOut', { km: num(trip.max_offshore_km ?? 0) })} · {t('extendBeforeSignal')}
          </Text>
        </Card>
      ) : null}

      <Card>
        <View style={styles.rowBetween}>
          <SectionTitle>{t('conditionsNow')}</SectionTitle>
          {conditions ? <LevelPill level={conditions.level} /> : null}
        </View>
        {conditions ? (
          <>
            <Text style={styles.numbers}>
              {t('waves')} {num(conditions.wave_height)} m · {t('wind')} {num(conditions.wind_speed, 0)} km/h
              {conditions.wind_from ? ` ${t('from')} ${conditions.wind_from}` : ''} · {t('gusts')} {num(conditions.wind_gust, 0)}
              {conditions.current_speed != null ? ` · ${t('current')} ${num(conditions.current_speed)} km/h${conditions.current_to ? ` → ${conditions.current_to}` : ''}` : ''}
            </Text>
            {(() => {
              // Head wind and current for the run home, from where the boat is now.
              if (trip.last_lat == null || trip.last_lon == null) return null;
              const farEnough = Math.abs(trip.last_lat - trip.start_lat) + Math.abs(trip.last_lon - trip.start_lon) > 0.004;
              if (!farEnough) return null;
              const course = bearing(trip.last_lat, trip.last_lon, trip.start_lat, trip.start_lon);
              const head = along(conditions.wind_speed, conditions.wind_from_deg, course);
              const withCurrent = along(conditions.current_speed, conditions.current_to_deg, course);
              if (head == null && withCurrent == null) return null;
              return (
                <View style={styles.runHome}>
                  <Text style={styles.runHomeTitle}>{t('runHome')}</Text>
                  {head != null ? (
                    <Text style={styles.runHomeText}>
                      {head > 2 ? t('headWind', { n: num(Math.abs(head), 0) }) : head < -2 ? t('tailWind', { n: num(Math.abs(head), 0) }) : t('crossWind')}
                    </Text>
                  ) : null}
                  {withCurrent != null && Math.abs(withCurrent) >= 0.3 ? (
                    <Text style={styles.runHomeText}>
                      {withCurrent < 0 ? t('currentAgainst', { n: num(Math.abs(withCurrent)) }) : t('currentWith', { n: num(Math.abs(withCurrent)) })}
                    </Text>
                  ) : null}
                </View>
              );
            })()}
            <ReasonList reasons={conditions.reasons} />
            {!conditionsLive ? <Text style={styles.sub}>{t('savedForecast')}</Text> : null}
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

      <Card>
        <BuddyBoats />
      </Card>

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
  status: { borderRadius: 6, padding: 18, alignItems: 'center', gap: 2 },
  statusText: { fontSize: 22, fontWeight: '900', color: colors.white },
  statusLabel: { fontSize: 15, fontWeight: '700', color: colors.white, textAlign: 'center' },
  countdown: { fontSize: 52, fontWeight: '900', color: colors.white },
  numbers: { fontSize: 17, lineHeight: 25, fontWeight: '700', color: colors.ink, marginBottom: 8 },
  runHome: { backgroundColor: colors.sea, borderRadius: 6, padding: 14, marginBottom: 10 },
  runHomeTitle: { fontSize: 14, fontWeight: '700', color: '#C9D8EE' },
  runHomeText: { fontSize: 18, lineHeight: 25, fontWeight: '800', color: colors.white },
  scheduled: { gap: 6, paddingVertical: 6 },
  scheduledWhen: { fontSize: 18, fontWeight: '800', color: colors.ink, flexShrink: 1 },
  step: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 6 },
  stepPassed: { opacity: 0.45 },
  stepTime: { fontSize: 18, fontWeight: '900', color: colors.ink, width: 88 },
  stepLabel: { fontSize: 15, fontWeight: '600', color: colors.ink, flexShrink: 1 },
});
