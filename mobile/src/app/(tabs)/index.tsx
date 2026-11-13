import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { HourDetail, HourStrip, LevelPill, ReasonList, VerdictCard } from '../../components/forecast';
import { Banner, BigButton, Card, Disclaimer, SectionTitle } from '../../components/ui';
import { api } from '../../lib/api';
import { formatClock, formatDay } from '../../lib/format';
import { canSpeak, speak, startListening, stopSpeaking, voiceInputAvailable } from '../../lib/speech';
import { loadJson, saveJson, useApp } from '../../lib/store';
import { TOUCH, colors, levelColor, levelInk } from '../../lib/theme';
import type { Advice, Forecast, HourRisk } from '../../lib/types';

const CACHE_KEY = 'seasafe.forecast';
type Cached = { forecast: Forecast; savedAt: string; boat: string; lang: string };

export default function Home() {
  const { profile, t, setSimOpen } = useApp();
  const router = useRouter();

  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedHour, setSelectedHour] = useState<HourRisk | null>(null);

  const [question, setQuestion] = useState('');
  const [listening, setListening] = useState(false);
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [advice, setAdvice] = useState<Advice | null>(null);
  const [showWhy, setShowWhy] = useState(false);

  const stopRef = useRef<(() => void) | null>(null);
  const heardRef = useRef('');
  const releasedRef = useRef(false);
  const explainedRef = useRef(false);
  const canUseVoice = useMemo(() => voiceInputAvailable(), []);
  // The answer is spoken with the phone's own voices. Warn when it has none for this language.
  const [voiceMissing, setVoiceMissing] = useState(false);

  const boat = profile?.boat_type;
  const lang = profile?.language;
  const lat = profile?.home_lat;
  const lon = profile?.home_lon;

  const load = useCallback(async () => {
    if (boat === undefined || lang === undefined || lat === undefined || lon === undefined) return;
    try {
      const fresh = await api.forecast(lat, lon, boat, lang);
      const now = new Date().toISOString();
      setForecast(fresh);
      setSavedAt(now);
      setOffline(false);
      void saveJson(CACHE_KEY, { forecast: fresh, savedAt: now, boat, lang } satisfies Cached);
    } catch {
      setOffline(true);
      const cached = await loadJson<Cached>(CACHE_KEY);
      // Only show a cached forecast that was computed for this boat: verdicts differ by boat.
      if (cached && cached.boat === boat) {
        setForecast(cached.forecast);
        setSavedAt(cached.savedAt);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [boat, lang, lat, lon]);

  // Reload whenever the tab gains focus (boat, language or scenario may have changed), then every 5 minutes.
  useFocusEffect(
    useCallback(() => {
      void load();
      const id = setInterval(load, 5 * 60 * 1000);
      return () => clearInterval(id);
    }, [load]),
  );

  // A previous answer is for the old boat or language.
  useEffect(() => {
    setAdvice(null);
    setSelectedHour(null);
  }, [boat, lang]);

  useEffect(() => () => stopSpeaking(), []);

  useEffect(() => {
    let cancelled = false;
    if (lang) void canSpeak(lang).then((ok) => !cancelled && setVoiceMissing(!ok));
    return () => {
      cancelled = true;
    };
  }, [lang]);

  const ask = useCallback(
    async (text: string) => {
      const q = text.trim();
      if (!q || !profile) return;
      setAsking(true);
      setAskError(null);
      setShowWhy(false);
      try {
        const result = await api.ask(q, profile.home_lat, profile.home_lon, profile.boat_type, profile.language);
        setAdvice(result);
        setForecast(result);
        setOffline(false);
        speak(result.answer, profile.language);
      } catch {
        // No signal: answer from the forecast saved on this phone instead of going silent.
        // The verdict and times were computed by the risk engine when it was saved.
        const saved = forecast ?? (await loadJson<Cached>(CACHE_KEY))?.forecast ?? null;
        const savedFor = savedAt ? formatClock(new Date(savedAt)) : null;
        const lower = q.toLowerCase();
        const dayIndex = lower.includes('day after') || q.includes('മറ്റന്നാൾ') ? 2 : lower.includes('tomorrow') || q.includes('നാളെ') ? 1 : 0;
        const day = saved && saved.boat_type === profile.boat_type ? saved.days[dayIndex] : undefined;
        if (saved && day && savedFor) {
          const answer = `${[t('today'), t('tomorrow'), t('dayAfter')][dayIndex]}: ${day.short_answer} ${t('offlineAnswer', { time: savedFor })} ${saved.advisory}`;
          setAdvice({
            ...saved,
            question: q,
            day_index: dayIndex,
            date: day.date,
            verdict: day.verdict,
            verdict_word: day.verdict_word,
            window: day.window,
            return_by: day.return_by,
            confidence: 'low',
            reasons: day.reasons,
            answer,
            short_answer: day.short_answer,
            source: 'template',
          });
          setOffline(true);
          speak(answer, profile.language);
        } else {
          setAskError(t('noConnection'));
        }
      } finally {
        setAsking(false);
      }
    },
    [profile, t, forecast, savedAt],
  );

  const micDown = async () => {
    if (!profile || listening || asking) return;
    stopSpeaking();
    setAskError(null);
    heardRef.current = '';
    explainedRef.current = false;
    releasedRef.current = false;
    setQuestion('');
    setListening(true);
    const stop = await startListening(profile.language, {
      onText: (text) => {
        heardRef.current = text;
        setQuestion(text);
      },
      onEnd: () => {
        stopRef.current = null;
        setListening(false);
        if (heardRef.current.trim()) void ask(heardRef.current);
        else if (!explainedRef.current) setAskError(t('didNotHear'));
      },
      onError: (code) => {
        // Say what went wrong, so the fisher knows whether to try again or type instead.
        if (code === 'not-allowed') setAskError(t('micDenied'));
        else if (code === 'network') setAskError(t('voiceNeedsNetwork'));
        else if (code === 'language-not-supported' || code === 'service-not-allowed') setAskError(t('voiceLanguageMissing'));
        else return;
        explainedRef.current = true; // keep this message: "did not hear" would hide the real cause
      },
    });
    if (!stop) {
      setListening(false);
      setAskError((current) => current ?? t('voiceUnavailable'));
      return;
    }
    stopRef.current = stop;
    if (releasedRef.current) stop(); // the finger was lifted while permissions were loading
  };

  const micUp = () => {
    releasedRef.current = true;
    stopRef.current?.();
  };

  const startTrip = () => {
    if (!advice) return;
    router.push({ pathname: '/trip', params: advice.return_by ? { returnBy: advice.return_by } : {} });
  };

  if (!profile) return null;
  const today = forecast?.days[0];
  const hazards = forecast?.reports_nearby.length ?? 0;
  const dayNames = [t('today'), t('tomorrow'), t('dayAfter')];

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Pressable onLongPress={() => setSimOpen(true)} delayLongPress={800}>
          <Text style={styles.brand}>🌊 {t('appName')}</Text>
        </Pressable>
        <Text style={styles.place} numberOfLines={1}>
          📍 {profile.home_name}
        </Text>
      </View>
      <ScrollView
        contentContainerStyle={styles.body}
        keyboardShouldPersistTaps="handled"
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setRefreshing(true);
              void load();
            }}
          />
        }
      >
        {offline && savedAt ? <Banner icon="📴" text={t('offlineBanner', { time: formatClock(new Date(savedAt)) })} /> : null}
        {offline && !forecast && !loading ? <Banner icon="📴" tone="warn" text={t('noConnection')} /> : null}
        {!offline && forecast?.stale ? (
          <Banner icon="⏳" tone="warn" text={(forecast.age_minutes ?? 0) > 180 ? t('staleOldBanner') : t('staleBanner')} />
        ) : null}
        {forecast && forecast.scenario !== 'real' ? <Banner icon="🎬" text={t('demoBanner', { mode: forecast.scenario })} /> : null}

        {forecast?.warnings.map((w) => (
          <Banner key={w.id} tone="danger" icon="🚨" text={`${t('officialWarning')}: ${w.title}. ${w.message}`} />
        ))}

        {loading && !forecast ? <ActivityIndicator size="large" color={colors.sea} style={styles.spinner} /> : null}

        {today ? (
          <VerdictCard
            day={today}
            title={t('today')}
            shortAnswer={advice && advice.day_index === 0 ? advice.short_answer : undefined}
          />
        ) : null}
        {!loading && !forecast ? <BigButton label={t('retry')} icon="🔄" onPress={load} /> : null}

        {forecast ? (
          <Card>
            <HourStrip hours={forecast.hourly} selected={selectedHour} onSelect={setSelectedHour} />
            {selectedHour ? <HourDetail hour={selectedHour} /> : null}
          </Card>
        ) : null}

        {/* Ask the Sea */}
        <Card style={styles.askCard}>
          <Pressable
            onPressIn={micDown}
            onPressOut={micUp}
            disabled={asking}
            accessibilityRole="button"
            accessibilityLabel={t('holdToAsk')}
            style={[styles.mic, listening && styles.micOn, asking && styles.micBusy]}
          >
            {asking ? <ActivityIndicator size="large" color={colors.white} /> : <Text style={styles.micIcon}>🎤</Text>}
          </Pressable>
          <Text style={styles.micLabel}>{asking ? t('thinking') : listening ? t('listening') : t('holdToAsk')}</Text>
          {!canUseVoice ? <Text style={styles.small}>{t('voiceUnavailable')}</Text> : null}
          {voiceMissing ? <Text style={styles.small}>🔇 {t('voiceOutputMissing')}</Text> : null}

          <Text style={styles.small}>{t('typeQuestion')}</Text>
          <View style={styles.askRow}>
            <TextInput
              value={question}
              onChangeText={setQuestion}
              placeholder={t('exampleQuestion')}
              placeholderTextColor={colors.inkSoft}
              accessibilityLabel={t('typeQuestion')}
              style={styles.askInput}
              returnKeyType="send"
              onSubmitEditing={() => ask(question)}
            />
            <Pressable
              onPress={() => ask(question)}
              disabled={asking || !question.trim()}
              accessibilityRole="button"
              accessibilityLabel={t('ask')}
              style={[styles.askButton, (asking || !question.trim()) && styles.askButtonOff]}
            >
              <Text style={styles.askButtonText}>➤</Text>
            </Pressable>
          </View>
          {askError ? <Text style={styles.error}>⚠ {askError}</Text> : null}
        </Card>

        {advice ? (
          <View style={[styles.answer, { borderColor: levelColor[advice.verdict] }]}>
            <View style={[styles.answerHead, { backgroundColor: levelColor[advice.verdict] }]}>
              <Text style={[styles.answerDay, { color: levelInk[advice.verdict] }]}>{dayNames[advice.day_index]}</Text>
              <LevelPill level={advice.verdict} />
            </View>
            <View style={styles.answerBody}>
              <Text style={styles.answerQuestion}>“{advice.question}”</Text>
              <Text style={styles.answerText}>{advice.answer}</Text>
              {advice.window ? (
                <Text style={styles.answerWindow}>
                  🕓 {advice.window.start_label} – {advice.window.end_label}   ↩ {advice.window.return_by_label}
                </Text>
              ) : null}
              <Text style={styles.small}>
                {t(`confidence_${advice.confidence}`)} · {advice.source === 'ai' ? t('sourceAi') : t('sourceTemplate')}
              </Text>

              <View style={styles.answerButtons}>
                <BigButton
                  label={t('why')}
                  icon={showWhy ? '▲' : '▼'}
                  onPress={() => setShowWhy((v) => !v)}
                  color={colors.line}
                  textColor={colors.ink}
                  style={styles.flex}
                />
                <BigButton
                  label={t('listenAgain')}
                  icon="🔊"
                  onPress={() => speak(advice.answer, profile.language)}
                  color={colors.line}
                  textColor={colors.ink}
                  style={styles.flex}
                />
              </View>
              {showWhy ? <ReasonList reasons={advice.reasons} /> : null}
              {advice.verdict !== 'UNSAFE' ? (
                <BigButton label={t('startThisTrip')} icon="⛵" onPress={startTrip} color={colors.safe} />
              ) : null}
            </View>
          </View>
        ) : null}

        <Pressable
          onPress={() => router.push('/watch')}
          accessibilityRole="button"
          style={[styles.hazardChip, hazards > 0 && styles.hazardChipOn]}
        >
          <Text style={styles.hazardText}>
            {hazards > 0 ? '⚠️ ' : '✔ '}
            {hazards === 0 ? t('noHazards') : hazards === 1 ? t('hazardNear') : t('hazardsNear', { n: hazards })}
          </Text>
          <Text style={styles.hazardText}>›</Text>
        </Pressable>

        {forecast && forecast.best_days.length > 0 ? (
          <Card>
            <SectionTitle>{t('bestDays')}</SectionTitle>
            <View style={styles.bestRow}>
              {forecast.best_days.slice(0, 3).map((d) => (
                <View key={d.date} style={[styles.bestDay, { borderColor: levelColor[d.verdict] }]}>
                  <Text style={styles.bestDayName}>{formatDay(d.date)}</Text>
                  <LevelPill level={d.verdict} />
                  <Text style={styles.small}>{t('safeHours', { n: d.safe_daylight_hours })}</Text>
                </View>
              ))}
            </View>
          </Card>
        ) : null}

        <Disclaimer />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  screen: { flex: 1, backgroundColor: colors.bg },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 8, gap: 12 },
  brand: { fontSize: 24, fontWeight: '900', color: colors.sea },
  place: { fontSize: 16, fontWeight: '700', color: colors.ink, flexShrink: 1 },
  body: { paddingHorizontal: 16, paddingBottom: 150, gap: 14 },
  spinner: { marginVertical: 40 },
  askCard: { alignItems: 'center', gap: 8 },
  mic: {
    width: 132,
    height: 132,
    borderRadius: 66,
    backgroundColor: colors.sea,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 6,
    borderColor: '#9DB4CC',
  },
  micOn: { backgroundColor: colors.unsafe, borderColor: '#F5B5BA', transform: [{ scale: 1.08 }] },
  micBusy: { backgroundColor: colors.inkSoft },
  micIcon: { fontSize: 58 },
  micLabel: { fontSize: 20, fontWeight: '800', color: colors.ink },
  small: { fontSize: 14, color: colors.inkSoft, textAlign: 'center' },
  askRow: { flexDirection: 'row', gap: 8, alignSelf: 'stretch' },
  askInput: {
    flex: 1,
    minHeight: TOUCH,
    borderWidth: 2,
    borderColor: colors.line,
    borderRadius: 12,
    paddingHorizontal: 14,
    fontSize: 17,
    color: colors.ink,
    backgroundColor: colors.white,
  },
  askButton: { width: TOUCH + 4, minHeight: TOUCH, borderRadius: 12, backgroundColor: colors.sea, alignItems: 'center', justifyContent: 'center' },
  askButtonOff: { opacity: 0.4 },
  askButtonText: { fontSize: 24, color: colors.white, fontWeight: '900' },
  error: { fontSize: 15, fontWeight: '700', color: colors.unsafe, textAlign: 'center' },
  answer: { borderRadius: 18, borderWidth: 3, backgroundColor: colors.card, overflow: 'hidden' },
  answerHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, paddingVertical: 10 },
  answerDay: { fontSize: 20, fontWeight: '900' },
  answerBody: { padding: 14, gap: 10 },
  answerQuestion: { fontSize: 15, color: colors.inkSoft, fontStyle: 'italic' },
  answerText: { fontSize: 19, lineHeight: 28, color: colors.ink, fontWeight: '600' },
  answerWindow: { fontSize: 17, fontWeight: '800', color: colors.ink },
  answerButtons: { flexDirection: 'row', gap: 8 },
  hazardChip: {
    minHeight: TOUCH + 4,
    borderRadius: 14,
    backgroundColor: colors.card,
    borderWidth: 2,
    borderColor: colors.line,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  hazardChipOn: { backgroundColor: '#FDE9D5', borderColor: colors.caution },
  hazardText: { fontSize: 18, fontWeight: '800', color: colors.ink },
  bestRow: { flexDirection: 'row', gap: 8 },
  bestDay: { flex: 1, borderWidth: 2, borderRadius: 12, padding: 8, alignItems: 'center', gap: 6 },
  bestDayName: { fontSize: 16, fontWeight: '800', color: colors.ink },
});
