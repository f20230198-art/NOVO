import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Animated, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon, LevelMark, type IconName } from '../../components/art';
import { HarbourMouthCard, HourDetail, HourStrip, LevelPill, ReasonList, SeaPanel } from '../../components/forecast';
import { BLUE_SCALES, LeafletMap, type MapMarker, type SeaMode } from '../../components/LeafletMap';
import { MapSheet } from '../../components/MapSheet';
import { FadeIn } from '../../components/trip/parts';
import { BigButton, Disclaimer, SectionTitle } from '../../components/ui';
import { api } from '../../lib/api';
import { formatClock, formatDay, formatHour, num } from '../../lib/format';
import { fetchSeaGrid, gridHourIndex, seaLayerAt, seaSummary, type SeaGrid } from '../../lib/seaGrid';
import { canSpeak, speak, startListening, stopSpeaking, voiceInputAvailable } from '../../lib/speech';
import { loadJson, saveJson, useApp } from '../../lib/store';
import { TOUCH, colors, display, levelColor, levelInk, reportIcon } from '../../lib/theme';
import type { Advice, DaySummary, Forecast, HourRisk } from '../../lib/types';

const CACHE_KEY = 'seasafe.forecast';
const GRID_CACHE_KEY = 'seasafe.seagrid';
const LAYER_KEY = 'seasafe.maplayer';
type Cached = { forecast: Forecast; savedAt: string; boat: string; lang: string };

export default function Home() {
  const { profile, t, setSimOpen } = useApp();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedHour, setSelectedHour] = useState<HourRisk | null>(null);
  const [grid, setGrid] = useState<SeaGrid | null>(null);
  // The fisher's map layer, remembered on this phone. Waves by default.
  const [seaMode, setSeaMode] = useState<SeaMode>('waves');
  const [recenterKey, setRecenterKey] = useState(0);
  useEffect(() => {
    void loadJson<SeaMode>(LAYER_KEY).then((saved) => {
      if (saved === 'waves' || saved === 'wind' || saved === 'depth' || saved === 'off') setSeaMode(saved);
    });
  }, []);
  const chooseLayer = (mode: SeaMode) => {
    setSeaMode(mode);
    void saveJson(LAYER_KEY, mode);
  };
  const [focused, setFocused] = useState(true);
  const [peekHeight, setPeekHeight] = useState(150);
  const [screenHeight, setScreenHeight] = useState(0);
  const [topHeight, setTopHeight] = useState(0);

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
    }
  }, [boat, lang, lat, lon]);

  // The map's sea state. Separate from the verdict and allowed to fail quietly: the map then
  // shows no texture, and the verdict is unaffected (it never reads the grid).
  const loadGrid = useCallback(async () => {
    if (lat === undefined || lon === undefined) return;
    try {
      const g = await fetchSeaGrid(lat, lon);
      setGrid(g);
      void saveJson(GRID_CACHE_KEY, g);
    } catch {
      const cached = await loadJson<SeaGrid>(GRID_CACHE_KEY);
      if (cached && Math.abs(cached.center.lat - lat) < 0.01 && Math.abs(cached.center.lon - lon) < 0.01) {
        setGrid((current) => current ?? cached);
      }
    }
  }, [lat, lon]);

  // Reload whenever the tab gains focus (boat, language or scenario may have changed), then every 5 minutes.
  useFocusEffect(
    useCallback(() => {
      setFocused(true);
      void load();
      void loadGrid();
      const id = setInterval(() => {
        void load();
        void loadGrid();
      }, 5 * 60 * 1000);
      return () => {
        clearInterval(id);
        setFocused(false); // stop animating the waves behind other tabs
      };
    }, [load, loadGrid]),
  );

  // A previous answer is for the old boat or language. Reset while rendering (not in an
  // effect), so the stale answer is never painted for a frame.
  const answerKey = `${boat}|${lang}`;
  const [answerFor, setAnswerFor] = useState(answerKey);
  if (answerFor !== answerKey) {
    setAnswerFor(answerKey);
    setAdvice(null);
    setSelectedHour(null);
  }

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

  // ---- map ----
  const center = useMemo(() => ({ lat: lat ?? 0, lon: lon ?? 0 }), [lat, lon]);
  // The map shows the hour picked in the strip; otherwise now.
  const gridIndex = useMemo(
    () => (grid ? gridHourIndex(grid, selectedHour ? new Date(selectedHour.time) : new Date()) : 0),
    [grid, selectedHour],
  );
  const sea = useMemo(() => (grid ? seaLayerAt(grid, gridIndex) : null), [grid, gridIndex]);
  const seaInfo = useMemo(() => (sea ? seaSummary(sea) : null), [sea]);
  const homeName = profile?.home_name;
  const reports = forecast?.reports_nearby;
  const markers = useMemo<MapMarker[]>(() => {
    if (lat === undefined || lon === undefined) return [];
    // The harbour is where the forecast is for. It is never drawn as the boat (CLAUDE.md rule 3).
    const list: MapMarker[] = [{ id: 'harbour', lat, lon, icon: '⚓', label: `${t('homeHarbour')}: ${homeName ?? ''}` }];
    for (const r of reports ?? []) {
      list.push({ id: `report-${r.id}`, lat: r.lat, lon: r.lon, icon: reportIcon[r.type], opacity: r.hidden ? 0.5 : 1, label: r.note ?? undefined });
    }
    return list;
  }, [lat, lon, homeName, reports, t]);

  if (!profile) return null;
  const today = forecast?.days[0];
  const hazards = forecast?.reports_nearby.length ?? 0;
  const dayNames = [t('today'), t('tomorrow'), t('dayAfter')];
  const mapHour = selectedHour ? `${dayNames[selectedHour.day_index] ?? ''} ${formatHour(selectedHour.hour)}` : formatClock(new Date());

  // Official warnings first and in full; the rest are one-line status strips.
  const notices: { key: string; tone: 'danger' | 'warn' | 'info'; icon: IconName; text: string }[] = [];
  for (const w of forecast?.warnings ?? []) notices.push({ key: `w${w.id}`, tone: 'danger', icon: 'alert', text: `${t('officialWarning')}: ${w.title}. ${w.message}` });
  if (offline && savedAt) notices.push({ key: 'off', tone: 'info', icon: 'offline', text: t('offlineBanner', { time: formatClock(new Date(savedAt)) }) });
  if (!offline && forecast?.stale)
    notices.push({ key: 'stale', tone: 'warn', icon: 'clock', text: (forecast.age_minutes ?? 0) > 180 ? t('staleOldBanner') : t('staleBanner') });
  if (forecast && forecast.scenario !== 'real') notices.push({ key: 'demo', tone: 'info', icon: 'play', text: t('demoBanner', { mode: forecast.scenario }) });

  const openHeight = Math.max(320, screenHeight - topHeight - 8);

  const peek = (
    <View style={styles.peek}>
      {today ? (
        <VerdictPeek day={today} title={t('today')} word={t(today.verdict)} text={advice && advice.day_index === 0 ? advice.short_answer : today.short_answer} noWindow={t('noWindow')} />
      ) : loading ? (
        <PeekSkeleton />
      ) : (
        // No forecast at all. Say so plainly: unknown is never shown as SAFE.
        <View style={[styles.verdict, styles.unknown]}>
          <View style={styles.verdictHead}>
            <Icon name="offline" size={30} color={colors.ink} />
            <Text style={[styles.unknownTitle, display]} numberOfLines={2}>
              {t('noConnection')}
            </Text>
          </View>
          <Pressable onPress={load} accessibilityRole="button" style={({ pressed }) => [styles.retry, pressed && styles.pressed]}>
            <Icon name="refresh" size={20} color={colors.white} />
            <Text style={styles.retryText}>{t('retry')}</Text>
          </Pressable>
        </View>
      )}
    </View>
  );

  return (
    <View style={styles.screen} onLayout={(e) => setScreenHeight(e.nativeEvent.layout.height)}>
      <LeafletMap
        fill
        hideZoomButtons
        center={center}
        zoom={10}
        markers={markers}
        sea={sea}
        seaMode={seaMode}
        recenterKey={recenterKey}
        paused={!focused}
        bottomInset={peekHeight}
        onMarkerPress={(id) => {
          if (id.startsWith('report-')) router.push('/watch');
        }}
      />

      {/* Header, alerts and the map key float over the map. */}
      <View
        pointerEvents="box-none"
        style={[styles.top, { paddingTop: insets.top + 8 }]}
        onLayout={(e) => setTopHeight(e.nativeEvent.layout.height)}
      >
        <View style={styles.headerRow}>
          <Pressable onLongPress={() => setSimOpen(true)} delayLongPress={800} style={styles.brandPill}>
            <Icon name="boat" size={22} color={colors.sea} weight={2.6} />
            <Text style={[styles.brand, display]}>{t('appName')}</Text>
          </Pressable>
          {/* Tap the harbour to bring the map back to it after panning away. */}
          <Pressable
            onPress={() => setRecenterKey((k) => k + 1)}
            accessibilityRole="button"
            accessibilityLabel={`${t('homeHarbour')}: ${profile.home_name}`}
            accessibilityHint={t('mapRecenter')}
            style={({ pressed }) => [styles.placePill, pressed && styles.pressed]}
          >
            <Icon name="anchor" size={16} color={colors.ink} />
            <Text style={styles.place} numberOfLines={1}>
              {profile.home_name}
            </Text>
          </Pressable>
        </View>
        {notices.map((n) => (
          <FadeIn key={n.key}>
            <View style={[styles.notice, styles[n.tone]]}>
              <Icon name={n.icon} size={18} color={n.tone === 'warn' ? colors.ink : colors.white} />
              <Text style={[styles.noticeText, n.tone === 'warn' && styles.inkText]} numberOfLines={n.tone === 'danger' ? 5 : 2}>
                {n.text}
              </Text>
            </View>
          </FadeIn>
        ))}
      </View>
      {seaInfo ? (
        <View pointerEvents="box-none" style={[styles.legendWrap, { bottom: peekHeight + 12 }]}>
          <FadeIn>
            <View style={styles.legend}>
              {seaMode !== 'off' && seaMode !== 'depth' ? <Text style={styles.legendHour}>{mapHour}</Text> : null}
              {seaMode === 'waves' && seaInfo.waveMax !== null ? (
                <>
                  <BlueRamp scale={BLUE_SCALES.waves} unit={t('unitM', { v: '' }).trim()} />
                  <Text style={styles.legendText}>
                    {t('waves')} {t('unitM', { v: `${num(seaInfo.waveMin)}–${num(seaInfo.waveMax)}` })}
                  </Text>
                </>
              ) : null}
              {seaMode === 'wind' && seaInfo.windMax !== null ? (
                <View style={styles.legendRow}>
                  <Icon name="wind" size={16} color={colors.sea} />
                  <Text style={styles.legendText}>
                    {t('wind')} {t('mapUpTo', { v: t('unitKmh', { v: num(seaInfo.windMax, 0) }) })}
                  </Text>
                </View>
              ) : null}
              {seaMode === 'depth' ? (
                seaInfo.depthMax !== null ? (
                  <>
                    <BlueRamp scale={BLUE_SCALES.depth} unit={t('unitM', { v: '' }).trim()} />
                    <Text style={styles.legendText}>
                      {t('depth')} {t('unitM', { v: `${num(seaInfo.depthMin, 0)}–${num(seaInfo.depthMax, 0)}` })}
                    </Text>
                    <Text style={styles.legendNote}>{t('mapDepthNote')}</Text>
                  </>
                ) : (
                  <Text style={styles.legendNote}>{t('mapDepthOffline')}</Text>
                )
              ) : null}
              {/* The run home into the wind (advisor.sea_out, now only): the head wind the arrows show. */}
              {!selectedHour && forecast?.sea?.head_wind_home != null && forecast.sea.head_wind_home > 2 ? (
                <View style={styles.headWind}>
                  <Icon name="house" size={15} color={colors.ink} />
                  <Text style={styles.headWindText}>{t('headWind', { n: num(forecast.sea.head_wind_home, 0) })}</Text>
                </View>
              ) : null}
              {grid?.stale ? <Text style={styles.legendNote}>{formatClock(new Date(grid.fetched_at))}</Text> : null}
              {/* Which layer is on the water; tap the lit one again for a bare map. Last in the box:
                  the box grows upwards, so the chips stay under the finger whatever the legend's height. */}
              <View style={styles.layerRow} accessibilityRole="radiogroup" accessibilityLabel={t('mapLayers')}>
                {LAYERS.map((l) => {
                  const on = seaMode === l.mode;
                  return (
                    <Pressable
                      key={l.mode}
                      onPress={() => chooseLayer(on ? 'off' : l.mode)}
                      accessibilityRole="radio"
                      accessibilityState={{ selected: on }}
                      accessibilityLabel={t(l.label)}
                      style={({ pressed }) => [styles.layerChip, on && styles.layerChipOn, pressed && styles.pressed]}
                    >
                      <Icon name={l.icon} size={16} color={on ? colors.white : colors.ink} />
                      <Text style={[styles.layerText, on && styles.layerTextOn]}>{t(l.label)}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          </FadeIn>
        </View>
      ) : null}

      <MapSheet peek={peek} openHeight={openHeight} onPeekHeight={setPeekHeight} openLabel={t('sheetOpen')} closeLabel={t('sheetClose')}>
        {forecast ? (
          <View>
            <HourStrip hours={forecast.hourly} selected={selectedHour} onSelect={(h) => setSelectedHour((cur) => (cur?.time === h.time ? null : h))} />
            {selectedHour ? <HourDetail hour={selectedHour} /> : null}
          </View>
        ) : null}

        <Pressable
          onPress={() => router.push('/watch')}
          accessibilityRole="button"
          style={({ pressed }) => [styles.row, hazards > 0 && styles.rowWarn, pressed && styles.pressed]}
        >
          <Icon name={hazards > 0 ? 'alert' : 'check'} size={24} color={colors.ink} weight={2.6} />
          <Text style={[styles.rowText, styles.flex]}>
            {hazards === 0 ? t('noHazards') : hazards === 1 ? t('hazardNear') : t('hazardsNear', { n: hazards })}
          </Text>
          <Icon name="chevRight" size={22} color={colors.ink} />
        </Pressable>

        {forecast?.harbour_mouth ? <HarbourMouthCard mouth={forecast.harbour_mouth} /> : null}
        {forecast?.sea ? <SeaPanel sea={forecast.sea} /> : null}

        {forecast && forecast.best_days.length > 0 ? (
          <View>
            <SectionTitle>{t('bestDays')}</SectionTitle>
            <View style={styles.bestRow}>
              {forecast.best_days.slice(0, 3).map((d) => (
                <View key={d.date} style={[styles.bestDay, { borderTopColor: levelColor[d.verdict] }]}>
                  <Text style={styles.bestDayName}>{formatDay(d.date)}</Text>
                  <LevelPill level={d.verdict} />
                  <Text style={styles.small}>{t('safeHours', { n: d.safe_daylight_hours })}</Text>
                </View>
              ))}
            </View>
          </View>
        ) : null}

        {/* Ask the Sea */}
        <View style={styles.askBox}>
          {canUseVoice ? (
            <View style={styles.micRow}>
              <Pressable
                onPressIn={micDown}
                onPressOut={micUp}
                disabled={asking}
                accessibilityRole="button"
                accessibilityLabel={t('holdToAsk')}
                style={[styles.mic, listening && styles.micOn, asking && styles.micBusy]}
              >
                {asking ? <ActivityIndicator color={colors.white} /> : <Icon name="mic" size={34} color={colors.white} weight={2} />}
              </Pressable>
              <Text style={styles.micLabel}>{asking ? t('thinking') : listening ? t('listening') : t('holdToAsk')}</Text>
            </View>
          ) : null}
          {voiceMissing ? <Text style={styles.small}>{t('voiceOutputMissing')}</Text> : null}
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
          {/* Full width: the floating SOS button covers the right edge of the screen. */}
          <Pressable
            onPress={() => ask(question)}
            disabled={asking || !question.trim()}
            accessibilityRole="button"
            accessibilityLabel={t('ask')}
            style={[styles.askButton, (asking || !question.trim()) && styles.askButtonOff]}
          >
            {asking ? (
              <ActivityIndicator color={colors.white} />
            ) : (
              <View style={styles.askButtonInner}>
                <Icon name="send" size={22} color={colors.white} />
                <Text style={styles.askButtonText}>{t('ask')}</Text>
              </View>
            )}
          </Pressable>
          {askError ? <Text style={styles.error}>{askError}</Text> : null}
        </View>

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
                <View style={styles.answerWindowRow}>
                  <Icon name="clock" size={20} color={colors.ink} />
                  <Text style={styles.answerWindow}>
                    {advice.window.start_label} – {advice.window.end_label}
                  </Text>
                  <Icon name="back" size={20} color={colors.ink} />
                  <Text style={styles.answerWindow}>{advice.window.return_by_label}</Text>
                </View>
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
              {advice.verdict !== 'UNSAFE' ? <BigButton label={t('startThisTrip')} icon="⛵" onPress={startTrip} color={colors.safe} /> : null}
            </View>
          </View>
        ) : null}

        <Disclaimer />
      </MapSheet>
    </View>
  );
}

const LAYERS: { mode: Exclude<SeaMode, 'off'>; label: 'waves' | 'wind' | 'depth'; icon: IconName }[] = [
  { mode: 'waves', label: 'waves', icon: 'wave' },
  { mode: 'wind', label: 'wind', icon: 'wind' },
  { mode: 'depth', label: 'depth', icon: 'depth' },
];

// OSM paints open water this colour; the map's blue sits on top of it with some transparency.
const OSM_WATER = [170, 211, 223];

/** The map's blue scale as swatches, each blended over OSM water so it matches the map. */
function BlueRamp({ scale, unit }: { scale: readonly (readonly number[])[]; unit: string }) {
  return (
    <View>
      <View style={styles.ramp}>
        {scale.map(([v, r, g, b, a]) => {
          const mix = (c: number, i: number) => Math.round(c * a + OSM_WATER[i] * (1 - a));
          return <View key={v} style={[styles.rampStep, { backgroundColor: `rgb(${mix(r, 0)},${mix(g, 1)},${mix(b, 2)})` }]} />;
        })}
      </View>
      <View style={styles.rampLabels}>
        {scale.map(([v], i) => (
          <Text key={v} style={i === scale.length - 1 ? styles.rampLabelLast : styles.rampLabel} numberOfLines={1}>
            {v}
            {i === scale.length - 1 ? `+ ${unit}` : ''}
          </Text>
        ))}
      </View>
    </View>
  );
}

/** The verdict at the top of the sheet: one painted block, nothing competing with it. */
function VerdictPeek({ day, title, word, text, noWindow }: { day: DaySummary; title: string; word: string; text: string; noWindow: string }) {
  const fg = levelInk[day.verdict];
  const ground = levelColor[day.verdict];
  return (
    <FadeIn>
      <View style={[styles.verdict, { backgroundColor: ground }]} accessible accessibilityLabel={`${title}. ${word}. ${text}`}>
        <View style={styles.verdictHead}>
          <LevelMark level={day.verdict} size={34} color={fg} ground={ground} />
          <Text style={[styles.verdictWord, display, { color: fg }]} numberOfLines={1} adjustsFontSizeToFit>
            {word}
          </Text>
          <Text style={[styles.verdictDay, { color: fg }]}>{title}</Text>
        </View>
        <Text style={[styles.verdictText, { color: fg }]} numberOfLines={2}>
          {text}
        </Text>
        <View style={styles.verdictWindow}>
          {day.window ? (
            <>
              <Icon name="clock" size={17} color={fg} />
              <Text style={[styles.verdictWindowText, display, { color: fg }]}>
                {day.window.start_label} – {day.window.end_label}
              </Text>
              <Icon name="back" size={17} color={fg} />
              <Text style={[styles.verdictWindowText, display, { color: fg }]}>{day.window.return_by_label}</Text>
            </>
          ) : (
            <Text style={[styles.verdictWindowText, { color: fg }]}>{noWindow}</Text>
          )}
        </View>
      </View>
    </FadeIn>
  );
}

/** Same size as the verdict block, so nothing jumps when the forecast arrives. */
function PeekSkeleton() {
  const [pulse] = useState(() => new Animated.Value(0.45));
  useEffect(() => {
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 650, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.45, duration: 650, useNativeDriver: true }),
      ]),
    );
    anim.start();
    return () => anim.stop();
  }, [pulse]);
  return (
    <Animated.View style={[styles.verdict, styles.skeleton, { opacity: pulse }]}>
      <View style={[styles.bone, { width: '55%', height: 32 }]} />
      <View style={[styles.bone, { width: '92%', height: 15, marginTop: 10 }]} />
      <View style={[styles.bone, { width: '64%', height: 15, marginTop: 7 }]} />
    </Animated.View>
  );
}

const chip = { backgroundColor: colors.card, borderWidth: 2, borderColor: colors.ink, borderRadius: 6, elevation: 3 } as const;

const styles = StyleSheet.create({
  flex: { flex: 1 },
  screen: { flex: 1, backgroundColor: '#cfe3f1' },
  top: { position: 'absolute', left: 0, right: 0, top: 0, paddingHorizontal: 12, gap: 8 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  brandPill: { ...chip, flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, height: 44 },
  brand: { fontSize: 21, lineHeight: 26, fontWeight: '900', color: colors.sea, letterSpacing: 0.5 },
  placePill: { ...chip, flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, height: 44, flexShrink: 1 },
  place: { fontSize: 15, fontWeight: '800', color: colors.ink, flexShrink: 1 },
  notice: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, borderRadius: 6, paddingHorizontal: 12, paddingVertical: 9, elevation: 3 },
  danger: { backgroundColor: colors.unsafe },
  warn: { backgroundColor: colors.caution },
  info: { backgroundColor: colors.seaDeep },
  noticeText: { flex: 1, color: colors.white, fontSize: 14, fontWeight: '700', lineHeight: 19 },
  inkText: { color: colors.ink },
  legendWrap: { position: 'absolute', left: 12 },
  legend: { ...chip, paddingHorizontal: 10, paddingVertical: 7, gap: 4 },
  legendHour: { fontSize: 12, fontWeight: '800', color: colors.inkSoft },
  legendRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  ramp: { flexDirection: 'row', alignSelf: 'flex-start', borderRadius: 2, overflow: 'hidden', borderWidth: 1, borderColor: colors.line },
  rampStep: { width: 30, height: 12 },
  rampLabels: { flexDirection: 'row', alignSelf: 'flex-start' },
  rampLabel: { width: 30, fontSize: 11, fontWeight: '700', color: colors.inkSoft },
  rampLabelLast: { fontSize: 11, fontWeight: '700', color: colors.inkSoft },
  // Wraps rather than clips if a translation runs long.
  layerRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 4 },
  layerChip: { flexDirection: 'row', alignItems: 'center', gap: 4, minHeight: 40, paddingHorizontal: 9, borderRadius: 4, borderWidth: 2, borderColor: colors.ink, backgroundColor: colors.card },
  layerChipOn: { backgroundColor: colors.sea, borderColor: colors.sea },
  layerText: { fontSize: 13, fontWeight: '800', color: colors.ink },
  layerTextOn: { color: colors.white },
  legendText: { fontSize: 13, fontWeight: '800', color: colors.ink },
  legendNote: { fontSize: 11, color: colors.inkSoft },
  headWind: { flexDirection: 'row', alignItems: 'flex-start', gap: 5, backgroundColor: colors.caution, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 4, maxWidth: 200 },
  headWindText: { flex: 1, fontSize: 12, lineHeight: 16, fontWeight: '800', color: colors.ink },
  peek: { paddingHorizontal: 14, paddingBottom: 12 },
  // The SOS button floats over the bottom-right of the closed sheet: keep the text clear of it.
  verdict: { borderRadius: 8, paddingVertical: 12, paddingLeft: 14, paddingRight: 100, minHeight: 122 },
  verdictHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  verdictWord: { fontSize: 32, lineHeight: 38, fontWeight: '900', flexShrink: 1 },
  verdictDay: { fontSize: 12, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase', opacity: 0.9 },
  verdictText: { fontSize: 16, fontWeight: '700', lineHeight: 21, marginTop: 4 },
  verdictWindow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 6 },
  verdictWindowText: { fontSize: 16, fontWeight: '900', marginRight: 8 },
  skeleton: { backgroundColor: colors.sand },
  bone: { borderRadius: 4, backgroundColor: colors.line },
  unknown: { backgroundColor: colors.sand, gap: 10, justifyContent: 'center' },
  unknownTitle: { fontSize: 20, fontWeight: '900', color: colors.ink, flexShrink: 1 },
  retry: { flexDirection: 'row', alignItems: 'center', gap: 8, alignSelf: 'flex-start', backgroundColor: colors.sea, borderRadius: 4, paddingHorizontal: 16, minHeight: 48 },
  retryText: { fontSize: 17, fontWeight: '900', color: colors.white },
  small: { fontSize: 14, color: colors.inkSoft, textAlign: 'center' },
  row: {
    minHeight: TOUCH + 4,
    borderRadius: 6,
    backgroundColor: colors.card,
    borderWidth: 2,
    borderColor: colors.ink,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  rowWarn: { backgroundColor: colors.caution },
  pressed: { opacity: 0.75 },
  rowText: { fontSize: 17, fontWeight: '800', color: colors.ink },
  bestRow: { flexDirection: 'row', gap: 8 },
  bestDay: { flex: 1, borderTopWidth: 6, paddingTop: 8, alignItems: 'flex-start', gap: 6 },
  bestDayName: { fontSize: 16, fontWeight: '800', color: colors.ink },
  askBox: { gap: 8, backgroundColor: colors.bg, borderRadius: 6, padding: 12 },
  micRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  mic: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.sea, alignItems: 'center', justifyContent: 'center', borderWidth: 4, borderColor: colors.ink },
  micOn: { backgroundColor: colors.unsafe, transform: [{ scale: 1.08 }] },
  micBusy: { backgroundColor: colors.inkSoft },
  micLabel: { fontSize: 19, fontWeight: '900', color: colors.ink, flexShrink: 1 },
  askInput: {
    minHeight: TOUCH,
    borderWidth: 2,
    borderColor: colors.ink,
    borderRadius: 4,
    paddingHorizontal: 14,
    fontSize: 17,
    color: colors.ink,
    backgroundColor: colors.white,
  },
  askButton: { minHeight: TOUCH, borderRadius: 4, backgroundColor: colors.sea, alignItems: 'center', justifyContent: 'center' },
  askButtonInner: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  askButtonOff: { opacity: 0.4 },
  askButtonText: { fontSize: 20, color: colors.white, fontWeight: '900' },
  error: { fontSize: 15, fontWeight: '700', color: colors.unsafe, textAlign: 'center' },
  answer: { borderRadius: 6, borderWidth: 3, backgroundColor: colors.card, overflow: 'hidden' },
  answerHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, paddingVertical: 10 },
  answerDay: { fontSize: 20, fontWeight: '900' },
  answerBody: { padding: 14, gap: 10 },
  answerQuestion: { fontSize: 15, color: colors.inkSoft, fontStyle: 'italic' },
  answerText: { fontSize: 19, lineHeight: 28, color: colors.ink, fontWeight: '600' },
  answerWindowRow: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
  answerWindow: { fontSize: 18, fontWeight: '800', color: colors.ink, marginRight: 10 },
  answerButtons: { flexDirection: 'row', gap: 8 },
});
