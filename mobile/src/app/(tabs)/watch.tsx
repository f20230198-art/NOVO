import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { LeafletMap, type MapMarker } from '../../components/LeafletMap';
import { Banner, BigButton, Card, Field, Screen, SectionTitle } from '../../components/ui';
import { api } from '../../lib/api';
import { formatDuration } from '../../lib/format';
import { getWorkingPosition, type Point } from '../../lib/location';
import { useApp } from '../../lib/store';
import { REPORT_TYPES, TOUCH, colors, reportIcon } from '../../lib/theme';
import type { Report, ReportType } from '../../lib/types';

export default function SeaWatch() {
  const { profile, t } = useApp();
  const router = useRouter();
  const params = useLocalSearchParams<{ report?: string }>();

  const [reports, setReports] = useState<Report[]>([]);
  const [me, setMe] = useState<Point | null>(null);
  const [offline, setOffline] = useState(false);
  const [notice, setNotice] = useState<{ text: string; tone: 'info' | 'warn' } | null>(null);
  const [focus, setFocus] = useState<Point | null>(null);

  const [sheet, setSheet] = useState(false);
  const [type, setType] = useState<ReportType | null>(null);
  const [note, setNote] = useState('');
  const [anonymous, setAnonymous] = useState(false);
  const [sending, setSending] = useState(false);

  const homeLat = profile?.home_lat;
  const homeLon = profile?.home_lon;
  const home = useMemo<Point | null>(
    () => (homeLat === undefined || homeLon === undefined ? null : { lat: homeLat, lon: homeLon }),
    [homeLat, homeLon],
  );
  const origin = me ?? home;

  const load = useCallback(async () => {
    if (!origin) return;
    try {
      setReports(await api.reports(origin.lat, origin.lon, 25));
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, [origin]);

  // Refresh on focus and every 15 s, so a report from another phone appears live.
  useFocusEffect(
    useCallback(() => {
      void load();
      const id = setInterval(load, 15000);
      return () => clearInterval(id);
    }, [load]),
  );

  useEffect(() => {
    if (home) void getWorkingPosition(home, 6000).then(setMe);
  }, [home]);

  // Opened from the trip screen's "Report hazard" shortcut.
  useEffect(() => {
    if (params.report === '1') {
      setSheet(true);
      router.setParams({ report: undefined });
    }
  }, [params.report, router]);

  const markers = useMemo<MapMarker[]>(
    () =>
      reports.map((r) => ({
        id: String(r.id),
        lat: r.lat,
        lon: r.lon,
        icon: reportIcon[r.type] ?? '⚠️',
        opacity: 0.35 + 0.65 * r.life_left, // fades as it nears expiry
        label: t(`report_${r.type}`),
      })),
    [reports, t],
  );

  const vote = async (report: Report, dir: 'up' | 'down') => {
    try {
      const updated = await api.voteReport(report.id, dir);
      setReports((list) =>
        updated.hidden ? list.filter((r) => r.id !== report.id) : list.map((r) => (r.id === report.id ? { ...r, up: updated.up, down: updated.down } : r)),
      );
    } catch {
      setNotice({ text: t('noConnection'), tone: 'warn' });
    }
  };

  const send = async () => {
    if (!type || !origin) return;
    setSending(true);
    const position = home ? await getWorkingPosition(home) : origin;
    try {
      await api.createReport(type, position.lat, position.lon, note.trim(), anonymous);
      setSheet(false);
      setType(null);
      setNote('');
      setNotice({ text: t('reportSent'), tone: 'info' });
      setFocus(position);
      void load();
    } catch {
      setNotice({ text: t('reportFailed'), tone: 'warn' });
      setSheet(false);
    } finally {
      setSending(false);
    }
  };

  if (!profile || !origin) return null;
  const center = focus ?? origin;

  return (
    <Screen title={t('tabWatch')}>
      {offline ? <Banner icon="📴" text={t('noConnection')} /> : null}
      {notice ? <Banner text={notice.text} tone={notice.tone} icon={notice.tone === 'warn' ? '⚠' : '✔'} /> : null}

      <LeafletMap
        center={center}
        zoom={11}
        markers={markers}
        me={me}
        onMarkerPress={(id) => {
          const r = reports.find((x) => String(x.id) === id);
          if (r) setFocus({ lat: r.lat, lon: r.lon });
        }}
      />

      <BigButton label={t('newReport')} icon="➕" onPress={() => setSheet(true)} color={colors.caution} textColor={colors.ink} style={styles.tall} />

      <SectionTitle>{t('reportsNearby')}</SectionTitle>
      {reports.length === 0 ? <Text style={styles.empty}>{t('noReports')}</Text> : null}
      {reports.map((r) => {
        const left = new Date(r.expires_at).getTime() - Date.now();
        return (
          <Card key={r.id} style={{ opacity: 0.55 + 0.45 * r.life_left }}>
            <Pressable onPress={() => setFocus({ lat: r.lat, lon: r.lon })} style={styles.reportHead}>
              <Text style={styles.reportIcon}>{reportIcon[r.type] ?? '⚠️'}</Text>
              <View style={styles.flex}>
                <Text style={styles.reportTitle}>{t(`report_${r.type}`)}</Text>
                <Text style={styles.reportSub}>
                  {r.distance_km !== null ? `${t('kmAway', { n: r.distance_km })} · ` : ''}
                  {t('expiresIn', { t: formatDuration(left) })}
                </Text>
                <Text style={styles.reportSub}>{t('by', { name: r.reporter ?? t('someone') })}</Text>
              </View>
            </Pressable>
            {r.note ? <Text style={styles.reportNote}>{r.note}</Text> : null}
            <View style={styles.voteRow}>
              <Pressable onPress={() => vote(r, 'up')} accessibilityRole="button" accessibilityLabel="Confirm" style={styles.vote}>
                <Text style={styles.voteText}>👍 {r.up}</Text>
              </Pressable>
              <Pressable onPress={() => vote(r, 'down')} accessibilityRole="button" accessibilityLabel="Dispute" style={styles.vote}>
                <Text style={styles.voteText}>👎 {r.down}</Text>
              </Pressable>
            </View>
          </Card>
        );
      })}

      <Modal visible={sheet} animationType="slide" transparent onRequestClose={() => setSheet(false)}>
        <View style={styles.backdrop}>
          <View style={styles.sheet}>
            <ScrollView contentContainerStyle={styles.sheetBody} keyboardShouldPersistTaps="handled">
              <Text style={styles.sheetTitle}>{t('whatDidYouSee')}</Text>
              <View style={styles.grid}>
                {REPORT_TYPES.map((rt) => {
                  const selected = rt === type;
                  return (
                    <Pressable
                      key={rt}
                      onPress={() => setType(rt)}
                      accessibilityRole="radio"
                      accessibilityState={{ selected }}
                      accessibilityLabel={t(`report_${rt}`)}
                      style={[styles.typeButton, selected && styles.typeButtonOn]}
                    >
                      <Text style={styles.typeIcon}>{reportIcon[rt]}</Text>
                      <Text style={[styles.typeLabel, selected && styles.typeLabelOn]} numberOfLines={2}>
                        {t(`report_${rt}`)}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
              <Field label={t('note')} value={note} onChangeText={setNote} maxLength={280} />
              <View style={styles.switchRow}>
                <Text style={styles.switchLabel}>🙈 {t('anonymous')}</Text>
                <Switch value={anonymous} onValueChange={setAnonymous} />
              </View>
              <BigButton label={t('send')} icon="📣" onPress={send} busy={sending} disabled={!type} color={colors.sea} />
              <BigButton label={t('cancel')} onPress={() => setSheet(false)} color={colors.line} textColor={colors.ink} />
            </ScrollView>
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  tall: { minHeight: 72 },
  empty: { fontSize: 16, color: colors.inkSoft },
  reportHead: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  reportIcon: { fontSize: 40 },
  reportTitle: { fontSize: 19, fontWeight: '800', color: colors.ink },
  reportSub: { fontSize: 14, color: colors.inkSoft },
  reportNote: { fontSize: 16, color: colors.ink, marginTop: 8, lineHeight: 22 },
  voteRow: { flexDirection: 'row', gap: 10, marginTop: 10 },
  vote: {
    flex: 1,
    minHeight: TOUCH,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: colors.line,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.white,
  },
  voteText: { fontSize: 20, fontWeight: '800', color: colors.ink },
  backdrop: { flex: 1, backgroundColor: 'rgba(11,37,69,0.55)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: colors.bg, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: '92%' },
  sheetBody: { padding: 16, gap: 12, paddingBottom: 28 },
  sheetTitle: { fontSize: 24, fontWeight: '900', color: colors.ink },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  typeButton: {
    width: '23%',
    flexGrow: 1,
    minHeight: 104,
    borderRadius: 14,
    borderWidth: 2,
    borderColor: colors.line,
    backgroundColor: colors.white,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 6,
  },
  typeButtonOn: { backgroundColor: colors.sea, borderColor: colors.sea },
  typeIcon: { fontSize: 38 },
  typeLabel: { fontSize: 13, fontWeight: '700', color: colors.ink, textAlign: 'center', marginTop: 4 },
  typeLabelOn: { color: colors.white },
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: TOUCH },
  switchLabel: { fontSize: 17, fontWeight: '700', color: colors.ink },
});
