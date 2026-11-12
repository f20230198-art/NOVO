import React, { useEffect, useRef } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { formatHour, num } from '../lib/format';
import { useApp } from '../lib/store';
import { colors, levelColor, levelIcon, levelInk } from '../lib/theme';
import type { DaySummary, HourRisk, Level, Reason } from '../lib/types';

/** Big coloured card: icon + verdict word + short answer + window + return-by. */
export function VerdictCard({ day, title, shortAnswer }: { day: DaySummary; title: string; shortAnswer?: string }) {
  const { t } = useApp();
  const fg = levelInk[day.verdict];
  return (
    <View
      style={[styles.verdict, { backgroundColor: levelColor[day.verdict] }]}
      accessible
      accessibilityLabel={`${title}. ${t(day.verdict)}. ${shortAnswer ?? day.short_answer}`}
    >
      <Text style={[styles.verdictTitle, { color: fg }]}>{title}</Text>
      <View style={styles.verdictRow}>
        <Text style={[styles.verdictIcon, { color: fg }]}>{levelIcon[day.verdict]}</Text>
        <Text style={[styles.verdictWord, { color: fg }]} adjustsFontSizeToFit numberOfLines={1}>
          {t(day.verdict)}
        </Text>
      </View>
      <Text style={[styles.verdictShort, { color: fg }]}>{shortAnswer ?? day.short_answer}</Text>
      {day.window ? (
        <View style={styles.windowRow}>
          <View style={styles.windowBox}>
            <Text style={[styles.windowLabel, { color: fg }]}>🕓 {t('bestWindow')}</Text>
            <Text style={[styles.windowValue, { color: fg }]}>
              {day.window.start_label} – {day.window.end_label}
            </Text>
          </View>
          <View style={styles.windowBox}>
            <Text style={[styles.windowLabel, { color: fg }]}>↩ {t('returnBy')}</Text>
            <Text style={[styles.windowValue, { color: fg }]}>{day.window.return_by_label}</Text>
          </View>
        </View>
      ) : null}
    </View>
  );
}

export function LevelPill({ level }: { level: Level }) {
  const { t } = useApp();
  return (
    <View style={[styles.pill, { backgroundColor: levelColor[level] }]}>
      <Text style={[styles.pillText, { color: levelInk[level] }]}>
        {levelIcon[level]} {t(level)}
      </Text>
    </View>
  );
}

/** The "Why?" list: each reason with its level marker and the numbers behind it. */
export function ReasonList({ reasons }: { reasons: Reason[] }) {
  const { t } = useApp();
  if (!reasons.length) return <Text style={styles.reasonText}>{t('noReasons')}</Text>;
  return (
    <View style={styles.reasons}>
      {reasons.map((r, i) => (
        <View key={`${r.factor}-${i}`} style={styles.reasonRow}>
          <View style={[styles.reasonDot, { backgroundColor: levelColor[r.level] }]}>
            <Text style={[styles.reasonDotText, { color: levelInk[r.level] }]}>{levelIcon[r.level]}</Text>
          </View>
          <Text style={styles.reasonText}>{r.text || r.factor}</Text>
        </View>
      ))}
    </View>
  );
}

const CELL = 34;

/** 3-day hourly strip. Each cell is coloured and carries an icon; tap one for its reasons. */
export function HourStrip({
  hours,
  selected,
  onSelect,
}: {
  hours: HourRisk[];
  selected: HourRisk | null;
  onSelect: (hour: HourRisk) => void;
}) {
  const { t } = useApp();
  const scroller = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const dayNames = [t('today'), t('tomorrow'), t('dayAfter')];
  const firstCurrent = hours.findIndex((h) => !h.past);

  useEffect(() => {
    if (firstCurrent > 1) {
      const id = setTimeout(() => scroller.current?.scrollTo({ x: (firstCurrent - 1) * CELL, animated: false }), 50);
      return () => clearTimeout(id);
    }
  }, [firstCurrent, hours.length]);

  return (
    <ScrollView ref={scroller} horizontal showsHorizontalScrollIndicator={false}>
      <View>
        <View style={styles.stripRow}>
          {hours.map((h) => (
            <View key={`d-${h.time}`} style={styles.dayCell}>
              {h.hour === 0 || h === hours[0] ? (
                <Text style={styles.dayLabel} numberOfLines={1}>
                  {dayNames[h.day_index] ?? ''}
                </Text>
              ) : null}
            </View>
          ))}
        </View>
        <View style={styles.stripRow}>
          {hours.map((h) => {
            const isSelected = selected?.time === h.time;
            return (
              <Pressable
                key={h.time}
                onPress={() => onSelect(h)}
                accessibilityLabel={`${dayNames[h.day_index] ?? ''} ${formatHour(h.hour)} ${t(h.level)}`}
                style={[
                  styles.cell,
                  { backgroundColor: levelColor[h.level], opacity: h.past ? 0.35 : 1 },
                  h.hour === 0 && styles.cellDayStart,
                  isSelected && styles.cellSelected,
                ]}
              >
                <Text style={[styles.cellIcon, { color: levelInk[h.level] }]}>{levelIcon[h.level]}</Text>
              </Pressable>
            );
          })}
        </View>
        <View style={styles.stripRow}>
          {hours.map((h) => (
            <View key={`h-${h.time}`} style={styles.hourCell}>
              {h.hour % 3 === 0 ? <Text style={styles.hourLabel}>{formatHour(h.hour)}</Text> : null}
            </View>
          ))}
        </View>
      </View>
    </ScrollView>
  );
}

export function HourDetail({ hour }: { hour: HourRisk }) {
  const { t } = useApp();
  const dayNames = [t('today'), t('tomorrow'), t('dayAfter')];
  return (
    <View style={styles.detail}>
      <View style={styles.detailHead}>
        <Text style={styles.detailTitle}>
          {dayNames[hour.day_index] ?? ''} {formatHour(hour.hour)}
        </Text>
        <LevelPill level={hour.level} />
      </View>
      <Text style={styles.detailNumbers}>
        🌊 {t('waves')} {num(hour.wave_height)} m · 💨 {t('wind')} {num(hour.wind_speed, 0)} km/h · {t('gusts')}{' '}
        {num(hour.wind_gust, 0)} km/h
      </Text>
      <ReasonList reasons={hour.reasons} />
    </View>
  );
}

const styles = StyleSheet.create({
  verdict: { borderRadius: 20, padding: 18 },
  verdictTitle: { fontSize: 16, fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase' },
  verdictRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 2 },
  verdictIcon: { fontSize: 44, fontWeight: '900' },
  verdictWord: { fontSize: 44, fontWeight: '900', flexShrink: 1 },
  verdictShort: { fontSize: 19, fontWeight: '700', lineHeight: 26, marginTop: 4 },
  windowRow: { flexDirection: 'row', gap: 10, marginTop: 12 },
  windowBox: { flex: 1, backgroundColor: 'rgba(255,255,255,0.22)', borderRadius: 12, padding: 10 },
  windowLabel: { fontSize: 13, fontWeight: '700' },
  windowValue: { fontSize: 18, fontWeight: '900', marginTop: 2 },
  pill: { borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, alignSelf: 'flex-start' },
  pillText: { fontSize: 15, fontWeight: '800' },
  reasons: { gap: 8 },
  reasonRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  reasonDot: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  reasonDotText: { fontSize: 14, fontWeight: '900' },
  reasonText: { flex: 1, fontSize: 16, lineHeight: 22, color: colors.ink },
  stripRow: { flexDirection: 'row' },
  dayCell: { width: CELL, height: 20, overflow: 'visible' },
  dayLabel: { width: CELL * 5, fontSize: 13, fontWeight: '800', color: colors.ink },
  cell: {
    width: CELL - 2,
    height: 56,
    marginRight: 2,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cellDayStart: { marginLeft: 0, borderLeftWidth: 3, borderLeftColor: colors.ink },
  cellSelected: { borderWidth: 3, borderColor: colors.ink },
  cellIcon: { fontSize: 15, fontWeight: '900' },
  hourCell: { width: CELL, height: 18 },
  hourLabel: { width: CELL * 2, fontSize: 12, color: colors.inkSoft },
  detail: { marginTop: 12, gap: 8 },
  detailHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  detailTitle: { fontSize: 18, fontWeight: '800', color: colors.ink },
  detailNumbers: { fontSize: 15, color: colors.inkSoft, lineHeight: 22 },
});
