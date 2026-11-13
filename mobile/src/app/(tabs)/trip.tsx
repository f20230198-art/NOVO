import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, StyleSheet, Text, Vibration, View } from 'react-native';

import { Icon } from '../../components/art';
import { BuddyBoats } from '../../components/buddies';
import { LevelPill, ReasonList } from '../../components/forecast';
import { HourList } from '../../components/trip/HourList';
import {
  DayAdvice,
  DayPicker,
  FadeIn,
  InfoRow,
  LateSteps,
  RiskNote,
  Stat,
  StepTitle,
  Suggestion,
  TimeStepper,
} from '../../components/trip/parts';
import {
  HALF_HOUR,
  HOUR,
  MIN,
  dayStart,
  defaultReturn,
  localDate,
  planRisk,
  roundUpToHalfHour,
  slotsBetween,
  suggestedDeparture,
  suggestedReturn,
} from '../../components/trip/plan';
import { TripTimeline } from '../../components/trip/TripTimeline';
import { clock, compass, dayShort, duration, kmh, metres } from '../../components/trip/words';
import { Banner, BigButton, Card, Screen, SectionTitle } from '../../components/ui';
import { api } from '../../lib/api';
import { along, bearing, num } from '../../lib/format';
import type { Translate } from '../../i18n';
import { getWorkingPosition } from '../../lib/location';
import { cancelNotification, notifyAt, notifyLocal } from '../../lib/notifications';
import { loadJson, saveJson, useApp } from '../../lib/store';
import { clearTrack, sendPosition } from '../../lib/trackQueue';
import { colors, display, levelColor } from '../../lib/theme';
import type { Forecast, HourRisk, Level, ScheduledTrip, Trip } from '../../lib/types';

const FIVE_MIN = 5 * MIN;
const ALARMS_KEY = 'seasafe.tripAlarms';
const PLAN_KEY = 'seasafe.tripPlan';
const FORECAST_KEY = 'seasafe.forecast'; // written by Home
const TRACK_KEY = 'seasafe.trackQueue'; // written by lib/trackQueue
const GRACE_MIN = 30; // server default for /trips/start
const CAUTION_TEXT = '#8A5A00';

/** A trip planned for later. Kept on the phone only: the watch starts when the fisher taps Start. */
type SavedPlan = { departAt: number; returnAt: number; reminderId: string | null };

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
    const id = await notifyAt(new Date(starts.getTime() - HOUR), t('headBack'), t('headBackSaved', { time: clock(t, starts) }));
    if (id) ids.push(id);
  }
  await saveJson(ALARMS_KEY, ids);
}

/** The saved-forecast hour that covers `now`, for when there is no signal. */
function snapshotHour(trip: Trip, now: number): HourRisk | null {
  return (
    trip.forecast_snapshot.find((h) => {
      const start = new Date(h.time).getTime();
      return start <= now && now < start + HOUR;
    }) ?? null
  );
}

const BAR_TEXT: Record<Level, 'barCalm' | 'barRough' | 'barDangerous'> = {
  SAFE: 'barCalm',
  CAUTION: 'barRough',
  UNSAFE: 'barDangerous',
};

export default function TripScreen() {
  const { profile, trip, setTrip, t, ensureRegistered, contacts } = useApp();
  const router = useRouter();
  const params = useLocalSearchParams<{ returnBy?: string }>();

  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; tone: 'info' | 'warn' } | null>(null);
  const [conditions, setConditions] = useState<HourRisk | null>(null);
  const [conditionsLive, setConditionsLive] = useState(false);
  const [scheduled, setScheduled] = useState<ScheduledTrip[]>([]);

  // Planning
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [dayIndex, setDayIndex] = useState(0);
  /** null = leave now. */
  const [departAt, setDepartAt] = useState<number | null>(null);
  const [returnAt, setReturnAt] = useState<number>(() => {
    // A return-by passed from Home wins, even before (or without) a forecast.
    const hint = params.returnBy ? new Date(params.returnBy).getTime() : NaN;
    return hint > Date.now() ? hint : roundUpToHalfHour(Date.now() + 4 * HOUR);
  });
  const [plan, setPlan] = useState<SavedPlan | null>(null);
  const [showWholeDay, setShowWholeDay] = useState(false);
  const touched = useRef(false); // the fisher changed something: stop applying suggestions
  const appliedParam = useRef<string | null>(null);

  // Tracking
  const [lastSent, setLastSent] = useState<number | null>(null);
  const [queued, setQueued] = useState(0);

  const lastHeadBack = useRef<string | null>(null);
  const lastStatus = useRef<string | null>(null);
  const warnedOffline = useRef<string | null>(null);
  const tripRef = useRef<Trip | null>(trip);
  useEffect(() => {
    tripRef.current = trip;
  }, [trip]);

  const tripId = trip?.id;
  const isOpen = Boolean(trip && trip.status !== 'returned');

  // Clock for the countdown.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 10000);
    return () => clearInterval(id);
  }, []);

  // Planned trip saved on this phone.
  useEffect(() => {
    void loadJson<SavedPlan>(PLAN_KEY).then((p) => p && setPlan(p));
  }, []);

  // Forecast for planning: the one Home saved for this boat first, then a fresh one.
  useEffect(() => {
    if (!profile || isOpen) return;
    let cancelled = false;
    (async () => {
      const cached = await loadJson<{ forecast: Forecast; boat: string; lang?: string }>(FORECAST_KEY);
      // Verdicts differ by boat, and the server writes its sentences in the asked language:
      // only use a cached forecast made for this boat and this language.
      if (!cancelled && cached && cached.boat === profile.boat_type && cached.lang === profile.language) {
        setForecast((f) => f ?? cached.forecast);
      }
      try {
        // Trips are planned from the home harbour: the same place Home shows, so the times match.
        const fresh = await api.forecast(profile.home_lat, profile.home_lon, profile.boat_type, profile.language);
        if (!cancelled) setForecast(fresh);
      } catch {
        // offline: keep the saved one
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [profile, isOpen]);

  const days = forecast?.days.slice(0, 3) ?? [];
  const day = days[dayIndex] ?? null;
  const hours = useMemo(() => forecast?.hourly ?? [], [forecast]);
  const departMs = departAt ?? now;

  /** Pre-fill the plan for a day from the server's safe window. Never lands in UNSAFE hours. */
  const applyDay = useCallback(
    (index: number, fc: Forecast, returnHint?: number) => {
      const d = fc.days[index];
      if (!d) return;
      const nowMs = Date.now();
      const isToday = d.date === localDate(nowMs);
      let depart = suggestedDeparture(d, nowMs) ?? (isToday ? nowMs : dayStart(d.date) + 5 * HOUR);
      if (depart <= nowMs + 15 * MIN) depart = nowMs;
      const back =
        returnHint && returnHint > depart + HALF_HOUR ? returnHint : suggestedReturn(d, depart) ?? defaultReturn(fc.hourly, depart);
      setDayIndex(index);
      setDepartAt(depart === nowMs ? null : depart);
      setReturnAt(back);
    },
    [],
  );

  // First suggestion once a forecast is here, or a return-by passed from Home.
  useEffect(() => {
    if (!forecast) return;
    const hint = params.returnBy ? new Date(params.returnBy).getTime() : NaN;
    if (params.returnBy && appliedParam.current !== params.returnBy && hint > Date.now()) {
      appliedParam.current = params.returnBy;
      const index = Math.max(0, forecast.days.findIndex((d) => d.date === localDate(hint)));
      touched.current = true; // the fisher chose this on Home
      applyDay(index, forecast, hint);
      return;
    }
    if (!touched.current) applyDay(dayIndex, forecast);
    // dayIndex is deliberately left out: changing day goes through pickDay.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forecast, params.returnBy, applyDay]);

  const pickDay = (index: number) => {
    touched.current = true;
    if (forecast) applyDay(index, forecast);
  };

  const shiftDepart = (delta: number) => {
    touched.current = true;
    // Step to the next / previous half hour on the clock (4:12 → 4:30, 5:00 → 4:30).
    const next =
      delta > 0 ? Math.floor(departMs / HALF_HOUR) * HALF_HOUR + HALF_HOUR : Math.ceil(departMs / HALF_HOUR) * HALF_HOUR - HALF_HOUR;
    const value = next <= Date.now() + 15 * MIN ? null : next;
    const ms = value ?? Date.now();
    setDepartAt(value);
    if (returnAt < ms + HALF_HOUR) setReturnAt(roundUpToHalfHour(ms + HOUR));
  };

  /** Tapped "Leave" on an hour in the hour list. */
  const leaveFromList = (ms: number) => {
    touched.current = true;
    const value = ms <= now + 15 * MIN ? null : ms;
    const leave = value ?? now;
    setDepartAt(value);
    if (returnAt < leave + HALF_HOUR) {
      setReturnAt((day && suggestedReturn(day, leave)) ?? defaultReturn(hours, leave));
    }
  };

  /** Tapped "Back by" on an hour in the hour list. */
  const backFromList = (ms: number) => {
    touched.current = true;
    setReturnAt(Math.max(ms, roundUpToHalfHour(departMs + HALF_HOUR)));
  };

  const shiftReturn = (delta: number) => {
    touched.current = true;
    setReturnAt((r) => Math.max(roundUpToHalfHour(departMs + HALF_HOUR), r + delta));
  };

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
      // Queued on the phone when there is no signal; uploaded with the next one that gets through.
      void sendPosition(current, position).then(async (sent) => {
        if (cancelled) return;
        if (sent) {
          setLastSent(Date.now());
          setQueued(0);
        } else {
          const q = (await loadJson<{ tripId: number }[]>(TRACK_KEY)) ?? [];
          if (!cancelled) setQueued(q.filter((p) => p.tripId === current.id).length);
        }
      });
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

  const clearPlan = async () => {
    if (plan?.reminderId) await cancelNotification(plan.reminderId);
    setPlan(null);
    await saveJson(PLAN_KEY, null);
  };

  const startWatched = async (back: number) => {
    if (!profile) return;
    if (back <= Date.now()) {
      setMessage({ text: t('returnInPast'), tone: 'warn' });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      if (!profile.token && !(await ensureRegistered())) throw new Error('offline');
      const position = await getWorkingPosition({ lat: profile.home_lat, lon: profile.home_lon });
      const started = await api.startTrip(new Date(back).toISOString(), position.lat, position.lon);
      lastHeadBack.current = null;
      lastStatus.current = started.status;
      warnedOffline.current = null;
      setLastSent(Date.now());
      setQueued(0);
      setTrip(started);
      void setAlarms(started, t);
      void clearPlan();
    } catch {
      setMessage({ text: t('tripNeedsServer'), tone: 'warn' });
    } finally {
      setBusy(false);
    }
  };

  const savePlan = async () => {
    const reminderId = await notifyAt(
      new Date(departMs),
      t('planReminderTitle'),
      t('planReminderBody', { time: clock(t, new Date(returnAt)) }),
    );
    const saved = { departAt: departMs, returnAt, reminderId };
    if (plan?.reminderId) await cancelNotification(plan.reminderId);
    setPlan(saved);
    await saveJson(PLAN_KEY, saved);
    setMessage({ text: t('planSaved', { time: clock(t, new Date(departMs)) }), tone: 'info' });
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
      setLastSent(null);
      setQueued(0);
      touched.current = false;
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
    const slots = slotsBetween(hours, departMs, returnAt);
    const risk = planRisk(slots);
    const firstBad = risk.unsafe ?? risk.caution;
    const sugDepart = day ? suggestedDeparture(day, now) : null;
    const sugReturn = day ? suggestedReturn(day, departMs) : null;
    // Only offer "be back by" as the fix when it actually ends the trip before the bad hours.
    const safeBy = sugReturn && firstBad && sugReturn <= firstBad.start ? sugReturn : null;
    const later = departAt !== null && departAt > now + 15 * MIN;
    const mouth = forecast?.harbour_mouth;
    const barAt = (ms: number) => mouth?.hourly.find((h) => {
      const s = new Date(h.time).getTime();
      return s <= ms && ms < s + HOUR;
    });
    const barOut = barAt(departMs);
    const barBack = barAt(returnAt);
    const askAt = returnAt + GRACE_MIN * MIN;
    const dayHours = day ? hours.filter((h) => h.day_index === day.day_index && new Date(h.time).getTime() + HOUR > now) : [];
    // By default only the trip's hours (plus one before and two after); the whole day on request.
    const listHours = showWholeDay
      ? dayHours
      : dayHours.filter((h) => {
          const s = new Date(h.time).getTime();
          return s + HOUR > departMs - HOUR && s < returnAt + 2 * HOUR;
        });
    const dayNames = [t('today'), t('tomorrow'), t('dayAfter')];
    const dayLabel = (ms: number) => {
      const d = localDate(ms);
      if (d === localDate(now)) return t('today');
      if (d === localDate(now + 24 * HOUR)) return t('tomorrow');
      return dayShort(t, d);
    };

    const onStart = () => {
      if (risk.unsafe) {
        Alert.alert(t('confirmUnsafeTitle'), t('confirmUnsafe', { time: clock(t, new Date(risk.unsafe.start)) }), [
          { text: t('cancel'), style: 'cancel' },
          { text: t('startAnyway'), style: 'destructive', onPress: () => void (later ? savePlan() : startWatched(returnAt)) },
        ]);
        return;
      }
      void (later ? savePlan() : startWatched(returnAt));
    };

    return (
      // Own key per view: switching plan ↔ active remounts the scroll view, so it opens at the top.
      <Screen key="plan" title={t('tabTrip')}>
        {message ? <Banner text={message.text} tone={message.tone} icon={message.tone === 'warn' ? 'alert' : 'check'} /> : null}

        {plan ? (
          <FadeIn>
            <Card style={styles.planCard}>
              <View style={styles.rowGap}>
                <Icon name="sail" size={26} color={colors.sea} />
                <Text style={[styles.planTitle, display]}>{t('plannedTrip')}</Text>
              </View>
              <Text style={[styles.planWhen, display]}>
                {dayLabel(plan.departAt)} · {clock(t, new Date(plan.departAt))} → {clock(t, new Date(plan.returnAt))}
              </Text>
              <Text style={styles.sub}>{t('notWatchedYet')}</Text>
              <BigButton
                label={busy ? t('starting') : t('startTrip')}
                icon="sail"
                onPress={() => void startWatched(plan.returnAt)}
                busy={busy}
                disabled={plan.returnAt <= now}
                color={colors.safe}
              />
              <BigButton label={t('cancelPlan')} onPress={() => void clearPlan()} color={colors.sand} textColor={colors.ink} />
            </Card>
          </FadeIn>
        ) : null}

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
                <BigButton label={t('startScheduled')} icon="sail" onPress={() => startFromSchedule(s)} busy={busy} color={colors.safe} />
              </View>
            ))}
          </Card>
        ) : null}

        {day ? (
          <FadeIn key={`advice-${day.date}`}>
            <DayAdvice
              day={day}
              dayName={dayNames[dayIndex] ?? dayShort(t, day.date)}
              hours={dayHours}
              warning={forecast?.warnings[0]?.title ?? null}
              headWindHome={forecast?.sea?.head_wind_home ?? null}
              now={now}
            />
          </FadeIn>
        ) : null}

        {/* 1. Leave */}
        <FadeIn>
          <Card style={styles.gap}>
            <StepTitle n={1}>{t('planStepLeave')}</StepTitle>
            {days.length > 0 ? <DayPicker days={days} selected={dayIndex} onSelect={pickDay} /> : null}
            {day && !day.window ? <Banner tone="warn" icon="alert" text={t('noSafeWindow')} /> : null}
            <TimeStepper
              label={t('leaveAt')}
              value={departAt === null ? t('now') : clock(t, new Date(departAt))}
              sub={departAt === null ? clock(t, new Date(now)) : dayLabel(departAt)}
              onMinus={() => shiftDepart(-HALF_HOUR)}
              onPlus={() => shiftDepart(HALF_HOUR)}
              minusDisabled={departAt === null}
            />
            {sugDepart !== null ? (
              <Suggestion
                icon="clock"
                text={
                  sugDepart <= now + 15 * MIN
                    ? t('leaveNow')
                    : t('leaveAtSafeStart', { time: clock(t, new Date(sugDepart)) })
                }
                selected={sugDepart <= now + 15 * MIN ? departAt === null : departAt === sugDepart}
                onPress={() => {
                  touched.current = true;
                  const v = sugDepart <= now + 15 * MIN ? null : sugDepart;
                  const leave = v ?? now;
                  setDepartAt(v);
                  if (returnAt < leave + HALF_HOUR && day) {
                    setReturnAt(suggestedReturn(day, leave) ?? defaultReturn(hours, leave));
                  }
                }}
              />
            ) : null}
          </Card>
        </FadeIn>

        {/* 2. Return */}
        <FadeIn delay={60}>
          <Card style={styles.gap}>
            <StepTitle n={2}>{t('planStepReturn')}</StepTitle>
            <TimeStepper
              label={t('returnTime')}
              value={clock(t, new Date(returnAt))}
              sub={`${dayLabel(returnAt)} · ${t('tripLength', { d: duration(t, returnAt - departMs) })}`}
              onMinus={() => shiftReturn(-HALF_HOUR)}
              onPlus={() => shiftReturn(HALF_HOUR)}
              minusDisabled={returnAt - HALF_HOUR < departMs + HALF_HOUR}
            />
            {sugReturn !== null ? (
              <Suggestion
                icon="back"
                text={t('backBySafe', { time: clock(t, new Date(sugReturn)) })}
                selected={returnAt === sugReturn}
                onPress={() => {
                  touched.current = true;
                  setReturnAt(sugReturn);
                }}
              />
            ) : null}
          </Card>
        </FadeIn>

        {dayHours.length > 0 ? (
          <FadeIn delay={90}>
            <Card style={styles.gap}>
              <View>
                <SectionTitle>{t('hourByHour')}</SectionTitle>
                <Text style={styles.sub}>{t('hourByHourHint')}</Text>
              </View>
              <HourList
                hours={listHours}
                mouth={forecast?.harbour_mouth?.hourly ?? []}
                departAt={departMs}
                returnAt={returnAt}
                now={now}
                onLeave={leaveFromList}
                onBack={backFromList}
              />
              {listHours.length < dayHours.length || showWholeDay ? (
                <BigButton
                  label={showWholeDay ? t('showTripHours') : t('showWholeDay')}
                  icon={showWholeDay ? 'chevUp' : 'chevDown'}
                  onPress={() => setShowWholeDay((v) => !v)}
                  color={colors.sand}
                  textColor={colors.ink}
                />
              ) : null}
            </Card>
          </FadeIn>
        ) : null}

        {/* 3. Check the sea */}
        <FadeIn delay={120}>
          <Card style={styles.gap}>
            <StepTitle n={3}>{t('planStepCheck')}</StepTitle>
            {hours.length > 0 ? (
              <>
                <TripTimeline hours={hours} departAt={departMs} returnAt={returnAt} />
                <RiskNote risk={risk} safeBy={safeBy} />
              </>
            ) : (
              <Banner tone="warn" icon="offline" text={t('noForecastYet')} />
            )}
            {mouth && (barOut || barBack) ? (
              <View style={styles.barBox}>
                <Text style={styles.barTitle}>{t('barTitle')}</Text>
                {[
                  { ms: departMs, h: barOut, label: t('barLeaving', { time: clock(t, new Date(departMs)) }), icon: 'sail' as const },
                  { ms: returnAt, h: barBack, label: t('barReturning', { time: clock(t, new Date(returnAt)) }), icon: 'anchor' as const },
                ].map((row) => (
                  <InfoRow
                    key={row.icon}
                    icon={row.icon}
                    title={row.label}
                    text={row.h ? t(BAR_TEXT[row.h.level]) : t('barUnknown')}
                    // Caution yellow is unreadable as text on sand, so it uses a dark amber.
                    color={!row.h ? colors.ink : row.h.level === 'CAUTION' ? CAUTION_TEXT : levelColor[row.h.level]}
                  />
                ))}
                <Text style={styles.small}>{t('barNote')}</Text>
              </View>
            ) : null}
          </Card>
        </FadeIn>

        <BigButton
          label={busy ? t('starting') : later ? t('remindMe', { time: clock(t, new Date(departMs)) }) : t('startTrip')}
          icon={later ? 'clock' : 'sail'}
          onPress={onStart}
          busy={busy}
          color={risk.unsafe ? colors.unsafe : later ? colors.sea : colors.safe}
          style={styles.tall}
        />
        {!later ? <Text style={styles.centerSub}>{t('startBackBy', { time: clock(t, new Date(returnAt)) })}</Text> : null}

        <Card>
          <SectionTitle>{t('ifLate')}</SectionTitle>
          {contacts.length === 0 ? <Banner tone="warn" icon="alert" text={t('noContactsWarn')} /> : null}
          <LateSteps
            steps={[
              { icon: 'question', when: t('lateAskWhen', { time: clock(t, new Date(askAt)), n: GRACE_MIN }), text: t('stepAsk') },
              { icon: 'message', when: t('lateContactsWhen'), text: `${t('lateContacts')} ${t('lateBuddies')}` },
              { icon: 'lifebuoy', when: t('lateSosWhen'), text: t('lateSos'), urgent: true },
            ]}
            footer={t('lateSosSlow')}
          />
        </Card>

        <Card>
          <BuddyBoats />
        </Card>
      </Screen>
    );
  }

  const startedMs = new Date(trip.started_at).getTime();
  const plannedMs = new Date(trip.planned_return).getTime();
  const remaining = plannedMs - now;
  const late = remaining < 0;
  const progress = Math.min(1, Math.max(0, (now - startedMs) / Math.max(1, plannedMs - startedMs)));
  const statusColor = trip.status === 'active' && !late ? colors.sea : colors.unsafe;
  const statusText =
    trip.status === 'emergency' ? t('tripEmergency') : trip.status === 'overdue' || late ? t('tripOverdue') : t('tripActive');
  const pingMs = lastSent ?? (trip.last_ping_at ? new Date(trip.last_ping_at).getTime() : null);
  const trackText =
    queued > 0
      ? t('trackQueued', { n: queued })
      : pingMs === null
        ? t('trackWaiting')
        : now - pingMs < MIN
          ? t('trackSentNow')
          : t('trackSent', { ago: duration(t, now - pingMs) });

  return (
    <Screen key="active" title={t('tabTrip')}>
      {message ? <Banner text={message.text} tone={message.tone} icon="alert" /> : null}
      {trip.head_back ? <Banner tone="danger" icon="alert" text={trip.head_back.message} /> : null}
      {dangerSoon ? (
        <Banner tone="danger" icon="alert" text={`${t('headBack')}: ${t('headBackSaved', { time: clock(t, new Date(dangerSoon.time)) })}`} />
      ) : null}

      <FadeIn style={[styles.status, { backgroundColor: statusColor }]}>
        <View style={styles.rowGap}>
          <Icon name={trip.status === 'active' && !late ? 'sail' : 'alert'} size={26} color={colors.white} />
          <Text style={[styles.statusText, display]}>{statusText}</Text>
        </View>
        <Text style={styles.statusLabel}>{late ? t('overdueBy') : t('timeLeft')}</Text>
        <Text style={[styles.countdown, display]}>{duration(t, remaining)}</Text>
        <View style={styles.progress}>
          <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
        </View>
        <View style={styles.stats}>
          <Stat label={t('elapsed')} value={duration(t, now - startedMs)} />
          <Stat label={t('returnBy')} value={clock(t, new Date(plannedMs))} />
        </View>
        {trip.status === 'emergency' || (trip.status === 'overdue' && trip.contacts_alerted) ? (
          <Text style={styles.statusLabel}>{t('familyAlerted')}</Text>
        ) : trip.status === 'overdue' || late ? (
          <Text style={styles.statusLabel}>{t('areYouBackBody')}</Text>
        ) : (
          <Text style={styles.statusLabel}>{t('graceNote', { n: trip.grace_minutes })}</Text>
        )}
      </FadeIn>

      {trip.auto_sos_sent ? <Banner tone="danger" icon="lifebuoy" text={t('autoSosSent')} /> : null}

      <BigButton label={t('imBack')} icon="house" onPress={finish} busy={busy} color={colors.safe} style={styles.tall} />
      {trip.status !== 'emergency' ? (
        <BigButton label={t('moreTime')} icon="timer" onPress={moreTime} busy={busy} color={colors.sand} textColor={colors.ink} />
      ) : null}

      <Card>
        <InfoRow
          icon={queued > 0 ? 'offline' : 'pin'}
          title={t('tracking')}
          text={trackText}
          color={queued > 0 ? colors.unsafe : colors.ink}
        />
        <Text style={[styles.small, styles.trackNote]}>{t('trackEvery')}</Text>
      </Card>

      {trip.forecast_snapshot.length > 0 ? (
        <Card style={styles.gap}>
          <SectionTitle>{t('tripSea')}</SectionTitle>
          <TripTimeline hours={trip.forecast_snapshot} departAt={startedMs} returnAt={plannedMs} now={now} />
        </Card>
      ) : null}

      {trip.escalation && trip.status !== 'emergency' ? (
        <Card>
          <SectionTitle>{t('ifLate')}</SectionTitle>
          <LateSteps
            steps={[
              {
                icon: 'question',
                when: clock(t, new Date(trip.escalation.ask_at)),
                text: t('stepAsk'),
                passed: new Date(trip.escalation.ask_at).getTime() <= now,
              },
              {
                icon: 'message',
                when: clock(t, new Date(trip.escalation.contacts_at)),
                text: `${t('lateContacts')} ${t('lateBuddies')}`,
                passed: new Date(trip.escalation.contacts_at).getTime() <= now,
              },
              {
                icon: 'lifebuoy',
                when: clock(t, new Date(trip.escalation.auto_sos_at)),
                text: t('stepAutoSos', { km: trip.escalation.offshore_km }),
                passed: new Date(trip.escalation.auto_sos_at).getTime() <= now,
                urgent: true,
              },
            ]}
            footer={`${t('furthestOut', { km: num(trip.max_offshore_km ?? 0) })} · ${t('extendBeforeSignal')} ${t('lateSosSlow')}`}
          />
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
              {t('waves')} {metres(t, num(conditions.wave_height))} · {t('wind')} {kmh(t, num(conditions.wind_speed, 0))}
              {conditions.wind_from ? ` ${t('windFrom', { dir: compass(t, conditions.wind_from) })}` : ''} · {t('gusts')}{' '}
              {kmh(t, num(conditions.wind_gust, 0))}
              {conditions.current_speed != null
                ? ` · ${t('current')} ${kmh(t, num(conditions.current_speed))}${conditions.current_to ? ` → ${compass(t, conditions.current_to)}` : ''}`
                : ''}
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

      <Card>
        <BuddyBoats />
      </Card>

      <BigButton
        label={t('reportHazard')}
        icon="alert"
        onPress={() => router.push({ pathname: '/watch', params: { report: '1' } })}
        color={colors.caution}
        textColor={colors.ink}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  gap: { gap: 14 },
  rowGap: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sub: { fontSize: 14, color: colors.inkSoft, lineHeight: 20 },
  small: { fontSize: 13, color: colors.inkSoft, lineHeight: 18 },
  centerSub: { fontSize: 14, color: colors.inkSoft, lineHeight: 20, textAlign: 'center', marginTop: -6 },
  tall: { minHeight: 84 },
  planCard: { gap: 10, borderTopColor: colors.sea },
  planTitle: { fontSize: 20, fontWeight: '800', color: colors.ink },
  planWhen: { fontSize: 26, fontWeight: '900', color: colors.ink },
  barBox: { gap: 10, backgroundColor: colors.sand, borderRadius: 6, padding: 12 },
  barTitle: { fontSize: 15, fontWeight: '800', color: colors.ink },
  status: { borderRadius: 6, padding: 18, alignItems: 'center', gap: 4 },
  statusText: { fontSize: 24, fontWeight: '900', color: colors.white },
  statusLabel: { fontSize: 15, fontWeight: '700', color: colors.white, textAlign: 'center' },
  countdown: { fontSize: 56, fontWeight: '900', color: colors.white },
  progress: { alignSelf: 'stretch', height: 8, borderRadius: 4, backgroundColor: 'rgba(255,255,255,0.25)', overflow: 'hidden', marginVertical: 6 },
  progressFill: { height: 8, backgroundColor: colors.white },
  stats: { flexDirection: 'row', alignSelf: 'stretch', marginBottom: 4 },
  trackNote: { marginTop: 6, marginLeft: 36 },
  numbers: { fontSize: 17, lineHeight: 25, fontWeight: '700', color: colors.ink, marginBottom: 8 },
  runHome: { backgroundColor: colors.sea, borderRadius: 6, padding: 14, marginBottom: 10 },
  runHomeTitle: { fontSize: 14, fontWeight: '700', color: '#C9D8EE' },
  runHomeText: { fontSize: 18, lineHeight: 25, fontWeight: '800', color: colors.white },
  scheduled: { gap: 6, paddingVertical: 6 },
  scheduledWhen: { fontSize: 18, fontWeight: '800', color: colors.ink, flexShrink: 1 },
});
