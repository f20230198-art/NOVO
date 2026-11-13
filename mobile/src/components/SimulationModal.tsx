import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../i18n';
import { api } from '../lib/api';
import { useAdoptDemoPersona } from '../lib/demoPersona';
import { useApp } from '../lib/store';
import { TOUCH, colors } from '../lib/theme';
import type { ReportType } from '../lib/types';
import { Field } from './ui';

const WEATHER: { mode: string; icon: string }[] = [
  { mode: 'real', icon: '🛰' },
  { mode: 'calm', icon: '☀️' },
  { mode: 'rough', icon: '🌊' },
  { mode: 'worsening', icon: '📉' },
  { mode: 'thunderstorm', icon: '⛈️' },
  { mode: 'heavy_rain', icon: '🌧' },
  { mode: 'strong_wind', icon: '💨' },
  { mode: 'high_swell', icon: '🌀' },
  { mode: 'storm', icon: '🌪' },
  { mode: 'cyclone', icon: '🚨' },
  { mode: 'kerala_week', icon: '🌴' },
];
const WARNINGS = ['cyclone', 'rough_sea', 'high_wind', 'lightning'] as const;
const HAZARDS: ReportType[] = ['harbour_mouth_rough', 'rough_sea', 'strong_current', 'boat_in_trouble', 'debris'];

/**
 * Simulation pop-up: switch the weather, post warnings and hazard reports, and act out trip
 * emergencies. Opened by long-pressing the app title on Home or Profile.
 */
export function SimulationModal() {
  const { profile, trip, apiUrl, setApiUrl, ensureRegistered, simOpen, setSimOpen, t } = useApp();
  const [current, setCurrent] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState(apiUrl);
  const [showServer, setShowServer] = useState(false);
  const adoptPersona = useAdoptDemoPersona();

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setUrl(apiUrl), [apiUrl]);
  useEffect(() => {
    if (!simOpen) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNote(null);
    api.health().then((h) => setCurrent(h.scenario)).catch(() => setNote(t('noConnection')));
  }, [simOpen, apiUrl, t]);

  if (!profile) return null;
  const home = { lat: profile.home_lat, lon: profile.home_lon };

  const run = async (label: string, action: () => Promise<unknown>) => {
    setBusy(true);
    setNote(null);
    try {
      await action();
      setNote(t('simDone', { what: label }));
    } catch {
      setNote(t('noConnection'));
    } finally {
      setBusy(false);
    }
  };

  const needTrip = (label: string, action: (id: number) => Promise<unknown>) =>
    trip && trip.status !== 'returned' ? run(label, () => action(trip.id)) : setNote(t('noActiveTrip'));

  return (
    <Modal visible={simOpen} transparent animationType="fade" onRequestClose={() => setSimOpen(false)}>
      <Pressable style={styles.backdrop} onPress={() => setSimOpen(false)} accessibilityLabel={t('close')}>
        {/* Inner Pressable stops taps inside the window from closing it. */}
        <Pressable style={styles.window} onPress={() => {}}>
          <View style={styles.head}>
            <Text style={styles.title}>🎛 {t('simTitle')}</Text>
            {busy ? <ActivityIndicator color={colors.sea} /> : null}
            <Pressable onPress={() => setSimOpen(false)} hitSlop={12} accessibilityRole="button" accessibilityLabel={t('close')}>
              <Text style={styles.x}>✕</Text>
            </Pressable>
          </View>
          {note ? <Text style={styles.note}>{note}</Text> : null}

          <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
            <Text style={styles.section}>{t('simWeather')}</Text>
            <View style={styles.grid}>
              {WEATHER.map((w) => (
                <Pressable
                  key={w.mode}
                  disabled={busy}
                  onPress={() =>
                    run(t(`sim_${w.mode}` as StringKey), async () => {
                      const r = await api.setScenario(w.mode, home.lat, home.lon);
                      setCurrent(r.mode);
                    })
                  }
                  style={[styles.tile, current === w.mode && styles.tileOn]}
                  accessibilityRole="button"
                  accessibilityState={{ selected: current === w.mode }}
                >
                  <Text style={styles.tileIcon}>{w.icon}</Text>
                  <Text style={[styles.tileText, current === w.mode && styles.tileTextOn]}>{t(`sim_${w.mode}` as StringKey)}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.section}>{t('simWarnings')}</Text>
            <View style={styles.chips}>
              {WARNINGS.map((k) => (
                <Chip key={k} label={t(`warn_${k}` as StringKey)} disabled={busy}
                  onPress={() => run(t(`warn_${k}` as StringKey), () => api.injectWarning(k, home.lat, home.lon))} />
              ))}
            </View>

            <Text style={styles.section}>{t('simHazards')}</Text>
            <View style={styles.chips}>
              {HAZARDS.map((h) => (
                <Chip key={h} label={t(`report_${h}` as StringKey)} disabled={busy}
                  onPress={() => run(t(`report_${h}` as StringKey), () => api.injectReport(h, home.lat + 0.01, home.lon - 0.01))} />
              ))}
            </View>

            <Text style={styles.section}>{t('simTrip')}</Text>
            <View style={styles.chips}>
              <Chip label={`⏩ ${t('fastForward')}`} disabled={busy}
                onPress={() => needTrip(t('fastForward'), async (id) => { await api.fastForward(id); await api.tick(); })} />
              <Chip label={`📡 ${t('loseSignal')}`} disabled={busy}
                onPress={() => needTrip(t('loseSignal'), async (id) => { await api.loseSignal(id); await api.tick(); })} />
              <Chip label={`🔁 ${t('runMonitor')}`} disabled={busy} onPress={() => run(t('runMonitor'), () => api.tick())} />
              <Chip label={`🌱 ${t('seedData')}`} disabled={busy} onPress={() => run(t('seedData'), () => api.seed())} />
              <Chip label={`🧑 ${t('demoFisher')}`} disabled={busy}
                onPress={() => run(t('demoFisherDone'), async () => { await adoptPersona(); setCurrent((await api.health()).scenario); })} />
            </View>

            <Pressable
              onPress={() =>
                run(t('simReset'), async () => {
                  await api.clearInjections();
                  setCurrent('real');
                })
              }
              disabled={busy}
              style={styles.reset}
              accessibilityRole="button"
            >
              <Text style={styles.resetText}>↺ {t('simReset')}</Text>
            </Pressable>

            <Pressable onPress={() => setShowServer((v) => !v)} accessibilityRole="button">
              <Text style={styles.link}>{showServer ? '▲' : '▼'} {t('serverSettings')}</Text>
            </Pressable>
            {showServer ? (
              <View>
                <Field label={t('serverUrl')} value={url} onChangeText={setUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" />
                <Chip
                  label={`💾 ${t('save')}`}
                  disabled={busy}
                  onPress={() =>
                    run(url, async () => {
                      await setApiUrl(url);
                      setCurrent((await api.health()).scenario);
                      await ensureRegistered();
                    })
                  }
                />
              </View>
            ) : null}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function Chip({ label, onPress, disabled }: { label: string; onPress: () => void; disabled?: boolean }) {
  return (
    <Pressable onPress={onPress} disabled={disabled} style={[styles.chip, disabled && styles.off]} accessibilityRole="button">
      <Text style={styles.chipText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(11,37,69,0.55)', justifyContent: 'center', padding: 16 },
  window: {
    maxHeight: '88%', backgroundColor: colors.bg, borderRadius: 20, overflow: 'hidden',
    borderWidth: 1, borderColor: colors.line, elevation: 12,
    shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 16, shadowOffset: { width: 0, height: 6 },
  },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingVertical: 12, backgroundColor: colors.card, borderBottomWidth: 1, borderColor: colors.line },
  title: { flex: 1, fontSize: 20, fontWeight: '900', color: colors.ink },
  x: { fontSize: 22, fontWeight: '800', color: colors.inkSoft, paddingHorizontal: 4 },
  note: { fontSize: 14, fontWeight: '700', color: colors.sea, paddingHorizontal: 16, paddingTop: 8 },
  body: { padding: 16, gap: 10 },
  section: { fontSize: 13, fontWeight: '800', color: colors.inkSoft, textTransform: 'uppercase', letterSpacing: 0.6, marginTop: 6 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tile: {
    width: '31%', minHeight: 72, borderRadius: 14, borderWidth: 2, borderColor: colors.line, backgroundColor: colors.white,
    alignItems: 'center', justifyContent: 'center', padding: 6,
  },
  tileOn: { backgroundColor: colors.sea, borderColor: colors.sea },
  tileIcon: { fontSize: 24 },
  tileText: { fontSize: 13, fontWeight: '800', color: colors.ink, textAlign: 'center' },
  tileTextOn: { color: colors.white },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: TOUCH - 4, borderRadius: 999, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.line, paddingHorizontal: 14, justifyContent: 'center' },
  chipText: { fontSize: 14, fontWeight: '700', color: colors.ink },
  off: { opacity: 0.5 },
  reset: { minHeight: TOUCH, borderRadius: 12, backgroundColor: colors.unsafe, alignItems: 'center', justifyContent: 'center', marginTop: 8 },
  resetText: { fontSize: 16, fontWeight: '900', color: colors.white },
  link: { fontSize: 14, fontWeight: '700', color: colors.inkSoft, marginTop: 8 },
});
