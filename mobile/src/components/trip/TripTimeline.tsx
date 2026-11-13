import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useApp } from '../../lib/store';
import { colors, levelColor, levelInk } from '../../lib/theme';
import type { HourRisk, Level } from '../../lib/types';
import { Icon, type IconName } from '../art';
import { HOUR, slotLevel, slotsBetween } from './plan';
import { axisHour, clock } from './words';

const UNKNOWN_BG = '#8E9AA3';
const LEVEL_ICON: Record<Level, IconName> = { SAFE: 'check', CAUTION: 'alert', UNSAFE: 'cross' };

/**
 * The hours of a trip as one bar, each hour coloured by the server's verdict.
 * Hours with no forecast are grey with "?" (never shown as SAFE). Markers show
 * departure, the planned return and (during a trip) now. One hour after the
 * return is shown too, so it is visible what the sea does if the boat is late.
 */
export function TripTimeline({
  hours,
  departAt,
  returnAt,
  now,
}: {
  hours: HourRisk[];
  departAt: number;
  returnAt: number;
  now?: number;
}) {
  const { t } = useApp();
  const from = Math.floor(departAt / HOUR) * HOUR;
  const to = Math.ceil(returnAt / HOUR) * HOUR + HOUR;
  const slots = slotsBetween(hours, from, to);
  if (slots.length === 0) return null;
  const span = slots.length * HOUR;
  const pct = (ms: number) => `${Math.min(100, Math.max(0, ((ms - from) / span) * 100))}%` as const;
  const labelEvery = slots.length <= 8 ? 1 : slots.length <= 16 ? 2 : 3;
  const compact = slots.length > 14;

  return (
    <View
      accessible
      accessibilityLabel={slots
        .map((s) => t('timelineA11y', { time: clock(t, new Date(s.start)), level: s.hour ? t(s.hour.level) : t('noForecast') }))
        .join(', ')}
    >
      <View style={styles.markers}>
        <Marker left={pct(departAt)} icon="sail" label={clock(t, new Date(departAt))} />
        <Marker left={pct(returnAt)} icon="back" label={clock(t, new Date(returnAt))} strong />
      </View>
      <View style={styles.bar}>
        {slots.map((s, i) => {
          const level = slotLevel(s);
          const after = s.start >= returnAt;
          return (
            <View
              key={s.start}
              style={[
                styles.cell,
                { backgroundColor: level ? levelColor[level] : UNKNOWN_BG, opacity: after ? 0.45 : 1 },
                i === 0 && styles.cellFirst,
                i === slots.length - 1 && styles.cellLast,
              ]}
            >
              {compact ? null : level ? (
                <Icon name={LEVEL_ICON[level]} size={16} color={levelInk[level]} weight={3} />
              ) : (
                <Text style={styles.unknownText}>?</Text>
              )}
            </View>
          );
        })}
        <View style={[styles.line, { left: pct(departAt) }]} />
        <View style={[styles.line, styles.lineReturn, { left: pct(returnAt) }]} />
        {now !== undefined && now >= from && now <= to ? <View style={[styles.now, { left: pct(now) }]} /> : null}
      </View>
      <View style={styles.hoursRow}>
        {slots.map((s, i) => (
          <View key={s.start} style={styles.hourCell}>
            {i % labelEvery === 0 ? (
              <Text style={styles.hourText} numberOfLines={1}>
                {axisHour(t, new Date(s.start))}
              </Text>
            ) : null}
          </View>
        ))}
      </View>
      <View style={styles.legend}>
        {(['SAFE', 'CAUTION', 'UNSAFE'] as const).map((l) => (
          <View key={l} style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: levelColor[l] }]} />
            <Text style={styles.legendText}>{t(l)}</Text>
          </View>
        ))}
        <View style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: UNKNOWN_BG }]} />
          <Text style={styles.legendText}>{t('noForecast')}</Text>
        </View>
      </View>
    </View>
  );
}

function Marker({ left, icon, label, strong }: { left: `${number}%`; icon: IconName; label: string; strong?: boolean }) {
  const at = parseFloat(left);
  // Near an edge, anchor the label to that edge instead of centring it, so it is not cut off.
  const edge =
    at < 18 ? { marginLeft: 0, alignItems: 'flex-start' as const } : at > 82 ? { marginLeft: -128, alignItems: 'flex-end' as const } : null;
  return (
    <View style={[styles.marker, { left }, edge]} pointerEvents="none">
      <View style={styles.markerRow}>
        <Icon name={icon} size={15} color={strong ? colors.ink : colors.inkSoft} />
        <Text style={[styles.markerText, strong && styles.markerStrong]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>
          {label}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  markers: { height: 26, marginHorizontal: 8 },
  // Wide enough for 'ഉച്ചയ്ക്ക് 12:30' at 13 sp.
  marker: { position: 'absolute', top: 0, width: 128, marginLeft: -64, alignItems: 'center' },
  markerRow: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  markerText: { fontSize: 13, fontWeight: '800', color: colors.inkSoft },
  markerStrong: { color: colors.ink },
  bar: { flexDirection: 'row', height: 48, marginHorizontal: 8 },
  cell: { flex: 1, marginRight: 2, alignItems: 'center', justifyContent: 'center' },
  cellFirst: { borderTopLeftRadius: 6, borderBottomLeftRadius: 6 },
  cellLast: { borderTopRightRadius: 6, borderBottomRightRadius: 6, marginRight: 0 },
  unknownText: { fontSize: 16, fontWeight: '900', color: colors.white },
  line: { position: 'absolute', top: -6, bottom: -6, width: 3, marginLeft: -1.5, backgroundColor: colors.inkSoft, borderRadius: 2 },
  lineReturn: { backgroundColor: colors.ink, width: 4, marginLeft: -2 },
  now: {
    position: 'absolute',
    top: -8,
    bottom: -8,
    width: 6,
    marginLeft: -3,
    borderRadius: 3,
    backgroundColor: colors.white,
    borderWidth: 2,
    borderColor: colors.ink,
  },
  hoursRow: { flexDirection: 'row', marginHorizontal: 8, marginTop: 6 },
  hourCell: { flex: 1, overflow: 'visible' },
  hourText: { fontSize: 12, color: colors.inkSoft, width: 40 },
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 10, marginHorizontal: 8 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  legendDot: { width: 12, height: 12, borderRadius: 2 },
  legendText: { fontSize: 12, fontWeight: '700', color: colors.inkSoft },
});
