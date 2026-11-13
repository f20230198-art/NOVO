import React, { useEffect, useRef } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { formatHour, num } from '../lib/format';
import { useApp } from '../lib/store';
import { colors, display, levelColor, levelInk } from '../lib/theme';
import type { DaySummary, HarbourMouth, HourRisk, Level, Reason, SeaState } from '../lib/types';
import { Icon, LevelMark, SeaScene, type IconName } from './art';

/**
 * The verdict, as a signal board: the picture, the mark and the word say the same thing,
 * then the two times a fisher needs (when to go, when to be back).
 */
export function VerdictCard({
  day,
  title,
  shortAnswer,
  place,
}: {
  day: DaySummary;
  title: string;
  shortAnswer?: string;
  place?: string;
}) {
  const { t } = useApp();
  const fg = levelInk[day.verdict];
  const ground = levelColor[day.verdict];
  return (
    <View
      style={[styles.verdict, { backgroundColor: ground }]}
      accessible
      accessibilityLabel={`${title}. ${t(day.verdict)}. ${shortAnswer ?? day.short_answer}`}
    >
      <SeaScene level={day.verdict} ink={fg} />
      <View style={styles.verdictBody}>
        <View style={styles.verdictRow}>
          <LevelMark level={day.verdict} size={46} color={fg} ground={ground} />
          <Text style={[styles.verdictWord, display, { color: fg }]} adjustsFontSizeToFit numberOfLines={1}>
            {t(day.verdict)}
          </Text>
        </View>
        <Text style={[styles.verdictWhen, { color: fg }]} numberOfLines={1}>
          {title}
          {place ? ` · ${place}` : ''}
        </Text>
        <Text style={[styles.verdictShort, { color: fg }]}>{shortAnswer ?? day.short_answer}</Text>
      </View>
      {day.window ? (
        <View style={[styles.windowRow, { borderTopColor: fg }]}>
          <View style={styles.windowBox}>
            <View style={styles.windowLabelRow}>
              <Icon name="clock" size={18} color={fg} />
              <Text style={[styles.windowLabel, { color: fg }]}>{t('bestWindow')}</Text>
            </View>
            <Text style={[styles.windowValue, display, { color: fg }]}>
              {day.window.start_label} – {day.window.end_label}
            </Text>
          </View>
          <View style={[styles.windowBox, styles.windowBoxRight, { borderLeftColor: fg }]}>
            <View style={styles.windowLabelRow}>
              <Icon name="back" size={18} color={fg} />
              <Text style={[styles.windowLabel, { color: fg }]}>{t('returnBy')}</Text>
            </View>
            <Text style={[styles.windowValue, display, { color: fg }]}>{day.window.return_by_label}</Text>
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
      <LevelMark level={level} size={18} color={levelInk[level]} ground={levelColor[level]} />
      <Text style={[styles.pillText, { color: levelInk[level] }]}>{t(level)}</Text>
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
          <LevelMark level={r.level} size={26} color={levelColor[r.level]} ground={levelInk[r.level]} />
          <Text style={styles.reasonText}>{r.text || r.factor}</Text>
        </View>
      ))}
    </View>
  );
}

const CELL = 34;

/** 3-day hourly strip. Each cell is coloured and carries a mark; tap one for its reasons. */
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
            // Height as well as colour: a rougher hour stands taller, like a tide gauge.
            const tall = h.level === 'UNSAFE' ? 56 : h.level === 'CAUTION' ? 44 : 32;
            return (
              <Pressable
                key={h.time}
                onPress={() => onSelect(h)}
                accessibilityLabel={`${dayNames[h.day_index] ?? ''} ${formatHour(h.hour)} ${t(h.level)}`}
                style={[styles.cellSlot, h.hour === 0 && styles.cellDayStart]}
              >
                <View
                  style={[
                    styles.cell,
                    { height: tall, backgroundColor: levelColor[h.level], opacity: h.past ? 0.3 : 1 },
                    isSelected && styles.cellSelected,
                  ]}
                />
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
      <View style={styles.factRow}>
        <Fact icon="wave" label={t('waves')} value={`${num(hour.wave_height)} m`} />
        <Fact
          icon="wind"
          label={t('wind')}
          value={`${num(hour.wind_speed, 0)} km/h${hour.wind_from ? ` ${hour.wind_from}` : ''}`}
          note={`${t('gusts')} ${num(hour.wind_gust, 0)}`}
        />
        {hour.current_speed != null ? (
          <Fact icon="compass" label={t('current')} value={`${num(hour.current_speed)} km/h${hour.current_to ? ` → ${hour.current_to}` : ''}`} />
        ) : null}
      </View>
      <ReasonList reasons={hour.reasons} />
    </View>
  );
}

function Fact({ icon, label, value, note, rotate }: { icon: IconName; label: string; value: string; note?: string; rotate?: number }) {
  return (
    <View style={styles.fact}>
      <View style={styles.factHead}>
        <Icon name={icon} size={20} color={colors.sea} rotate={rotate} />
        <Text style={styles.factLabel} numberOfLines={1}>
          {label}
        </Text>
      </View>
      <Text style={[styles.factValue, display]}>{value}</Text>
      {note ? <Text style={styles.factNote}>{note}</Text> : null}
    </View>
  );
}

/**
 * The sea right now: wind and where it comes from, the current and where it sets, the
 * tide, the depth, and what wind and current do to the run home.
 */
export function SeaPanel({ sea, headWind, againstCurrent }: { sea: SeaState; headWind?: number | null; againstCurrent?: number | null }) {
  const { t } = useApp();
  const head = headWind ?? sea.head_wind_home;
  const against = againstCurrent ?? sea.current_against_home;
  const tide = sea.tide_state === 'rising' ? t('tideRising') : sea.tide_state === 'falling' ? t('tideFalling') : sea.tide_state === 'slack' ? t('tideSlack') : undefined;
  return (
    <View style={styles.sea}>
      <Text style={styles.blockTitle}>{t('seaNow')}</Text>
      <View style={styles.factGrid}>
        <Fact
          icon="wind"
          label={t('wind')}
          value={`${num(sea.wind_speed, 0)} km/h`}
          note={sea.wind_from ? `${t('from')} ${sea.wind_from} · ${t('gusts')} ${num(sea.wind_gust, 0)}` : undefined}
        />
        <Fact
          icon="compass"
          label={t('current')}
          value={sea.current_speed != null ? `${num(sea.current_speed)} km/h` : '–'}
          note={sea.current_to ? `${t('towards')} ${sea.current_to}` : undefined}
        />
        <Fact icon="wave" label={t('waves')} value={`${num(sea.wave_height)} m`} note={sea.wave_period != null ? t('everySeconds', { n: num(sea.wave_period, 0) }) : undefined} />
        <Fact icon="tide" label={t('tide')} value={sea.tide_m != null ? `${sea.tide_m > 0 ? '+' : ''}${num(sea.tide_m)} m` : '–'} note={tide} rotate={sea.tide_state === 'falling' ? 180 : 0} />
        <Fact icon="depth" label={t('depth')} value={sea.depth_m != null ? `${num(sea.depth_m, 0)} m` : '–'} note={t('depthNote')} />
      </View>
      {head != null || against != null ? (
        <View style={styles.runHome}>
          <Icon name="house" size={22} color={colors.white} />
          <View style={styles.flex}>
            <Text style={styles.runHomeTitle}>{t('runHome')}</Text>
            {head != null ? (
              <Text style={styles.runHomeText}>
                {head > 2 ? t('headWind', { n: num(Math.abs(head), 0) }) : head < -2 ? t('tailWind', { n: num(Math.abs(head), 0) }) : t('crossWind')}
              </Text>
            ) : null}
            {against != null && Math.abs(against) >= 0.3 ? (
              <Text style={styles.runHomeText}>
                {against > 0 ? t('currentAgainst', { n: num(Math.abs(against)) }) : t('currentWith', { n: num(Math.abs(against)) })}
              </Text>
            ) : null}
          </View>
        </View>
      ) : null}
    </View>
  );
}

/**
 * Harbour mouth: a swell that is easy offshore breaks on the bar, worst on a falling tide.
 * Shows the crossing level now, today's crossing hours, and when it is calm enough to cross.
 */
export function HarbourMouthCard({ mouth }: { mouth: HarbourMouth }) {
  const { t } = useApp();
  const today = mouth.days[0];
  const hours = mouth.hourly.filter((h) => h.day_index === 0 && h.hour >= 3 && h.hour < 19);
  return (
    <View style={styles.mouth}>
      <View style={styles.detailHead}>
        <View style={styles.mouthTitleRow}>
          <Icon name="anchor" size={24} color={colors.ink} />
          <Text style={styles.blockTitle}>{t('barTitle')}</Text>
        </View>
        <LevelPill level={mouth.level} />
      </View>
      {mouth.breaker_m != null ? <Text style={[styles.mouthBig, display]}>{t('barBreaker', { m: num(mouth.breaker_m) })}</Text> : null}
      {mouth.long_swell ? <Text style={styles.mouthWhy}>{t('barLongSwell')}</Text> : null}
      {mouth.ebb ? <Text style={styles.mouthWhy}>{t('barEbb')}</Text> : null}

      <View style={styles.mouthStrip}>
        {hours.map((h) => (
          <View key={h.time} style={styles.mouthSlot}>
            <View style={[styles.mouthCell, { backgroundColor: levelColor[h.level], opacity: h.past ? 0.3 : 1 }]} />
            {h.hour % 3 === 0 ? <Text style={styles.mouthHour}>{formatHour(h.hour)}</Text> : null}
          </View>
        ))}
      </View>

      {today && today.windows.length > 0 ? (
        <Text style={styles.mouthWindow}>
          {t('barOpen')}: {today.windows.map((w) => `${w.start_label} – ${w.end_label}`).join(', ')}
        </Text>
      ) : (
        <Text style={styles.mouthWindow}>{t('barNoWindow')}</Text>
      )}
      {mouth.closes_label ? <Text style={styles.mouthWhy}>{t('barCloses', { time: mouth.closes_label })}</Text> : null}
      <Text style={styles.mouthNote}>{t('barNote')}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  verdict: { borderRadius: 6, overflow: 'hidden' },
  verdictBody: { paddingHorizontal: 18, paddingTop: 6, paddingBottom: 16 },
  verdictRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  verdictWord: { fontSize: 56, lineHeight: 64, fontWeight: '900', flexShrink: 1, letterSpacing: 0.5 },
  verdictWhen: { fontSize: 16, fontWeight: '700', marginTop: 2, opacity: 0.92 },
  verdictShort: { fontSize: 21, fontWeight: '700', lineHeight: 29, marginTop: 8 },
  windowRow: { flexDirection: 'row', borderTopWidth: 2 },
  windowBox: { flex: 1, paddingHorizontal: 18, paddingVertical: 12 },
  windowBoxRight: { borderLeftWidth: 2 },
  windowLabelRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  windowLabel: { fontSize: 14, fontWeight: '700' },
  windowValue: { fontSize: 24, lineHeight: 32, fontWeight: '900', marginTop: 2 },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 4, paddingHorizontal: 10, paddingVertical: 6, alignSelf: 'flex-start' },
  pillText: { fontSize: 15, fontWeight: '800' },
  reasons: { gap: 10 },
  reasonRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  reasonText: { flex: 1, fontSize: 16, lineHeight: 23, color: colors.ink },
  stripRow: { flexDirection: 'row', alignItems: 'flex-end' },
  dayCell: { width: CELL, height: 22, overflow: 'visible' },
  dayLabel: { width: CELL * 5, fontSize: 14, fontWeight: '800', color: colors.ink },
  cellSlot: { width: CELL, height: 60, justifyContent: 'flex-end', paddingRight: 3 },
  cell: { borderTopLeftRadius: 3, borderTopRightRadius: 3 },
  cellDayStart: { borderLeftWidth: 2, borderLeftColor: colors.ink, paddingLeft: 2 },
  cellSelected: { borderWidth: 3, borderColor: colors.ink },
  hourCell: { width: CELL, height: 20, borderTopWidth: 2, borderTopColor: colors.ink },
  hourLabel: { width: CELL * 2, fontSize: 13, color: colors.inkSoft, marginTop: 2 },
  detail: { marginTop: 14, gap: 12 },
  detailHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  detailTitle: { fontSize: 19, fontWeight: '800', color: colors.ink },
  factRow: { flexDirection: 'row', gap: 14, flexWrap: 'wrap' },
  factGrid: { flexDirection: 'row', flexWrap: 'wrap', rowGap: 16, columnGap: 12 },
  fact: { minWidth: 96, flexGrow: 1, flexBasis: '28%' },
  factHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  factLabel: { fontSize: 14, fontWeight: '700', color: colors.inkSoft, flexShrink: 1 },
  factValue: { fontSize: 24, lineHeight: 30, fontWeight: '900', color: colors.ink, marginTop: 2 },
  factNote: { fontSize: 13, lineHeight: 18, color: colors.inkSoft },
  sea: { gap: 14 },
  blockTitle: { fontSize: 20, fontWeight: '800', color: colors.ink },
  runHome: { flexDirection: 'row', gap: 12, alignItems: 'flex-start', backgroundColor: colors.sea, borderRadius: 6, padding: 14 },
  runHomeTitle: { fontSize: 14, fontWeight: '700', color: '#C9D8EE' },
  runHomeText: { fontSize: 18, lineHeight: 25, fontWeight: '800', color: colors.white },
  mouth: { gap: 8 },
  mouthTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexShrink: 1 },
  mouthBig: { fontSize: 26, lineHeight: 33, fontWeight: '900', color: colors.ink, marginTop: 4 },
  mouthWhy: { fontSize: 16, lineHeight: 23, color: colors.ink },
  mouthStrip: { flexDirection: 'row', marginTop: 8, marginBottom: 2 },
  mouthSlot: { flex: 1, height: 44 },
  mouthCell: { height: 20, marginRight: 2, borderRadius: 2 },
  mouthHour: { fontSize: 12, color: colors.inkSoft, marginTop: 3, width: 40 },
  mouthWindow: { fontSize: 18, lineHeight: 25, fontWeight: '800', color: colors.ink },
  mouthNote: { fontSize: 13, lineHeight: 18, color: colors.inkSoft, marginTop: 2 },
});
