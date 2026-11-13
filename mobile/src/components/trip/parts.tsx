import React, { useEffect, useState } from 'react';
import { Animated, Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';

import { num } from '../../lib/format';
import { useApp } from '../../lib/store';
import { TOUCH, colors, display, levelColor, levelInk } from '../../lib/theme';
import type { DaySummary, HourRisk, Level } from '../../lib/types';
import { Icon, LevelMark, type IconName } from '../art';
import type { PlanRisk } from './plan';
import { clock, dayShort } from './words';

/** Fades and slides its children in when it first appears. */
export function FadeIn({ children, delay = 0, style }: { children: React.ReactNode; delay?: number; style?: StyleProp<ViewStyle> }) {
  const [v] = useState(() => new Animated.Value(0));
  useEffect(() => {
    Animated.timing(v, { toValue: 1, duration: 260, delay, useNativeDriver: true }).start();
  }, [v, delay]);
  return (
    <Animated.View
      style={[style, { opacity: v, transform: [{ translateY: v.interpolate({ inputRange: [0, 1], outputRange: [12, 0] }) }] }]}
    >
      {children}
    </Animated.View>
  );
}

/** Step number + heading, so the plan reads as 1 → 2 → 3. */
export function StepTitle({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <View style={styles.stepTitle}>
      <View style={styles.stepNum}>
        <Text style={[styles.stepNumText, display]}>{n}</Text>
      </View>
      <Text style={[styles.stepTitleText, display]}>{children}</Text>
    </View>
  );
}

/** One big tile per forecast day, marked with the server's verdict for that day. */
export function DayPicker({
  days,
  selected,
  onSelect,
}: {
  days: DaySummary[];
  selected: number;
  onSelect: (index: number) => void;
}) {
  const { t } = useApp();
  const names = [t('today'), t('tomorrow'), t('dayAfter')];
  return (
    <View style={styles.dayRow}>
      {days.slice(0, 3).map((d, i) => {
        const on = i === selected;
        return (
          <Pressable
            key={d.date}
            onPress={() => onSelect(i)}
            accessibilityRole="radio"
            accessibilityState={{ selected: on }}
            accessibilityLabel={`${names[i] ?? dayShort(t, d.date)}, ${t(d.verdict)}`}
            style={({ pressed }) => [styles.day, on && styles.daySelected, pressed && styles.pressed]}
          >
            <Text style={[styles.dayName, display, on && styles.onText]} numberOfLines={1} adjustsFontSizeToFit>
              {names[i] ?? dayShort(t, d.date)}
            </Text>
            <Text style={[styles.dayDate, on && styles.onText]} numberOfLines={1} adjustsFontSizeToFit>
              {dayShort(t, d.date)}
            </Text>
            <View style={[styles.dayPill, { backgroundColor: levelColor[d.verdict] }]}>
              <Text style={[styles.dayPillText, { color: levelInk[d.verdict] }]} numberOfLines={1} adjustsFontSizeToFit>
                {t(d.verdict)}
              </Text>
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

/** A big clock with − / + buttons on either side. */
export function TimeStepper({
  label,
  value,
  onMinus,
  onPlus,
  minusDisabled,
  sub,
}: {
  label: string;
  value: string;
  onMinus: () => void;
  onPlus: () => void;
  minusDisabled?: boolean;
  sub?: string;
}) {
  const { t } = useApp();
  return (
    <View>
      <Text style={styles.stepperLabel}>{label}</Text>
      <View style={styles.stepper}>
        <RoundButton text={t('minus30')} onPress={onMinus} disabled={minusDisabled} a11y={t('minus30A11y', { label })} />
        <View style={styles.stepperValueBox}>
          <Text style={[styles.stepperValue, display]} adjustsFontSizeToFit numberOfLines={1} accessibilityLabel={`${label} ${value}`}>
            {value}
          </Text>
          {sub ? <Text style={styles.stepperSub}>{sub}</Text> : null}
        </View>
        <RoundButton text={t('plus30')} onPress={onPlus} a11y={t('plus30A11y', { label })} />
      </View>
    </View>
  );
}

function RoundButton({ text, onPress, disabled, a11y }: { text: string; onPress: () => void; disabled?: boolean; a11y: string }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={a11y}
      hitSlop={6}
      style={({ pressed }) => [styles.round, { opacity: disabled ? 0.35 : pressed ? 0.7 : 1 }]}
    >
      <Text style={styles.roundText}>{text}</Text>
    </Pressable>
  );
}

/** A wide tappable suggestion, e.g. "Be back by 11:30 AM (safe time ends)". */
export function Suggestion({
  icon,
  text,
  selected,
  onPress,
}: {
  icon: IconName;
  text: string;
  selected: boolean;
  onPress: () => void;
}) {
  const fg = selected ? colors.white : colors.ink;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      style={({ pressed }) => [styles.suggestion, selected && styles.suggestionOn, pressed && styles.pressed]}
    >
      <Icon name={selected ? 'check' : icon} size={22} color={fg} />
      <Text style={[styles.suggestionText, { color: fg }]}>{text}</Text>
    </Pressable>
  );
}

/** Plain warning under the timeline. Worst first: UNSAFE, then CAUTION, then missing forecast. */
export function RiskNote({ risk, safeBy }: { risk: PlanRisk; safeBy: number | null }) {
  const { t } = useApp();
  const at = (ms: number) => clock(t, new Date(ms));
  const backBy = safeBy ? t('planFixBackBy', { time: at(safeBy) }) : null;
  if (risk.unsafe) {
    return <Note level="UNSAFE" text={`${t('planHitsUnsafe', { time: at(risk.unsafe.start) })} ${backBy ?? t('planFixOtherDay')}`} />;
  }
  if (risk.caution) {
    return <Note level="CAUTION" text={`${t('planHitsCaution', { time: at(risk.caution.start) })} ${backBy ?? t('planTakeCare')}`} />;
  }
  if (risk.unknown) return <Note level="CAUTION" text={t('planNoForecast', { time: at(risk.unknown.start) })} />;
  return <Note level="SAFE" text={t('planAllSafe')} />;
}

function Note({ level, text }: { level: Level; text: string }) {
  const fg = levelInk[level];
  return (
    <FadeIn key={`${level}-${text}`} style={[styles.note, { backgroundColor: levelColor[level] }]}>
      <LevelMark level={level} size={30} color={fg} ground={levelColor[level]} />
      <Text style={[styles.noteText, { color: fg }]} accessibilityLiveRegion="polite">
        {text}
      </Text>
    </FadeIn>
  );
}

export type LateStep = { icon: IconName; when: string; text: string; passed?: boolean; urgent?: boolean };

/** "If you are late": what happens, in order, down a rope line. */
export function LateSteps({ steps, footer }: { steps: LateStep[]; footer?: string }) {
  return (
    <View>
      {steps.map((s, i) => (
        <View key={`${s.icon}-${i}`} style={[styles.lateRow, s.passed && styles.latePassed]}>
          <View style={styles.lateRail}>
            <View style={[styles.lateDot, s.urgent && styles.lateDotUrgent]}>
              <Icon name={s.icon} size={20} color={s.urgent ? colors.white : colors.ink} />
            </View>
            {i < steps.length - 1 ? <View style={styles.lateLine} /> : null}
          </View>
          <View style={styles.lateBody}>
            <Text style={styles.lateWhen}>{s.when}</Text>
            <Text style={styles.lateText}>{s.text}</Text>
          </View>
        </View>
      ))}
      {footer ? <Text style={styles.lateFooter}>{footer}</Text> : null}
    </View>
  );
}

/** Small label + value pair used in the active-trip header. */
export function Stat({ label, value, color = colors.white }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.stat}>
      <Text style={[styles.statLabel, { color }]}>{label}</Text>
      <Text style={[styles.statValue, display, { color }]} adjustsFontSizeToFit numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

/**
 * The forecast's advice for the chosen day, at the top of the planner. Everything here is the
 * server's: its short answer, its safe window and return-by, the first hour it did not mark
 * SAFE (with its own reason text), official warnings and the run-home figures when present.
 * Nothing is worked out or softened on the phone.
 */
export function DayAdvice({
  day,
  dayName,
  hours,
  warning,
  headWindHome,
  now,
}: {
  day: DaySummary;
  dayName: string;
  hours: HourRisk[];
  warning: string | null;
  headWindHome: number | null;
  now: number;
}) {
  const { t } = useApp();
  const at = (iso: string) => clock(t, new Date(iso));
  const windowEnd = day.window ? new Date(day.window.end).getTime() : 0;
  const upcoming = hours.filter((h) => new Date(h.time).getTime() + 60 * 60 * 1000 > now);
  // First hour the server did not mark SAFE: after the safe window if there is one.
  const bad =
    upcoming.find((h) => h.level !== 'SAFE' && new Date(h.time).getTime() >= windowEnd) ??
    upcoming.find((h) => h.level !== 'SAFE') ??
    null;
  const fg = levelInk[day.verdict];
  return (
    <View style={[styles.advice, { backgroundColor: levelColor[day.verdict] }]} accessibilityLiveRegion="polite">
      <View style={styles.adviceHead}>
        <LevelMark level={day.verdict} size={34} color={fg} ground={levelColor[day.verdict]} />
        <View style={styles.infoBody}>
          <Text style={[styles.adviceTitle, { color: fg }]}>{t('adviceTitle', { day: dayName })}</Text>
          <Text style={[styles.adviceShort, display, { color: fg }]}>{day.short_answer}</Text>
        </View>
      </View>
      {/* The server's short answer already states the safe window and return-by. */}
      {bad ? (
        <View style={styles.adviceRow}>
          <Icon name={bad.level === 'UNSAFE' ? 'cross' : 'alert'} size={20} color={fg} />
          <Text style={[styles.adviceText, { color: fg }]}>
            {t(bad.level === 'UNSAFE' ? 'adviceAvoid' : 'adviceCareFrom', { time: at(bad.time) })}
            {bad.reasons[0]?.text ? `: ${bad.reasons[0].text}` : ''}
          </Text>
        </View>
      ) : null}
      {warning ? (
        <View style={styles.adviceRow}>
          <Icon name="flag" size={20} color={fg} />
          <Text style={[styles.adviceText, { color: fg }]}>{t('adviceWarning', { title: warning })}</Text>
        </View>
      ) : null}
      {headWindHome != null && headWindHome > 2 ? (
        <View style={styles.adviceRow}>
          <Icon name="wind" size={20} color={fg} />
          <Text style={[styles.adviceText, { color: fg }]}>{t('headWind', { n: num(headWindHome, 0) })}</Text>
        </View>
      ) : null}
      <Text style={[styles.adviceSource, { color: fg }]}>{t('adviceSource')}</Text>
    </View>
  );
}

/** One line with an icon and text, used for GPS and harbour-mouth status. */
export function InfoRow({ icon, title, text, color = colors.ink }: { icon: IconName; title: string; text: string; color?: string }) {
  return (
    <View style={styles.info}>
      <Icon name={icon} size={24} color={color} />
      <View style={styles.infoBody}>
        <Text style={styles.infoTitle}>{title}</Text>
        <Text style={[styles.infoText, { color }]}>{text}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  pressed: { opacity: 0.75 },
  onText: { color: colors.white },
  stepTitle: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  stepNum: { width: 30, height: 30, borderRadius: 15, backgroundColor: colors.sea, alignItems: 'center', justifyContent: 'center' },
  stepNumText: { color: colors.white, fontWeight: '900', fontSize: 17 },
  stepTitleText: { fontSize: 21, fontWeight: '800', color: colors.ink, flexShrink: 1 },

  dayRow: { flexDirection: 'row', gap: 8 },
  day: {
    flex: 1,
    minHeight: 104,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: colors.line,
    backgroundColor: colors.card,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    paddingHorizontal: 4,
    gap: 4,
  },
  daySelected: { borderColor: colors.sea, backgroundColor: colors.sea },
  dayName: { fontSize: 18, fontWeight: '800', color: colors.ink },
  dayDate: { fontSize: 13, fontWeight: '600', color: colors.inkSoft },
  dayPill: { borderRadius: 4, paddingHorizontal: 8, paddingVertical: 3, marginTop: 2, maxWidth: '100%' },
  dayPillText: { fontSize: 12, fontWeight: '900' },

  stepperLabel: { fontSize: 15, fontWeight: '700', color: colors.inkSoft, marginBottom: 6 },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  stepperValueBox: { flex: 1, alignItems: 'center' },
  stepperValue: { fontSize: 44, fontWeight: '900', color: colors.ink },
  stepperSub: { fontSize: 13, fontWeight: '600', color: colors.inkSoft },
  round: {
    width: TOUCH + 8,
    height: TOUCH + 8,
    borderRadius: (TOUCH + 8) / 2,
    backgroundColor: colors.sand,
    alignItems: 'center',
    justifyContent: 'center',
  },
  roundText: { fontSize: 18, fontWeight: '900', color: colors.ink },

  suggestion: {
    minHeight: TOUCH,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: colors.safe,
    backgroundColor: colors.card,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  suggestionOn: { backgroundColor: colors.safe },
  suggestionText: { flex: 1, fontSize: 16, fontWeight: '800' },

  note: { flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 6, padding: 12 },
  noteText: { flex: 1, fontSize: 16, fontWeight: '700', lineHeight: 22 },

  lateRow: { flexDirection: 'row', gap: 12 },
  latePassed: { opacity: 0.45 },
  lateRail: { alignItems: 'center', width: 38 },
  lateDot: { width: 38, height: 38, borderRadius: 19, backgroundColor: colors.sand, alignItems: 'center', justifyContent: 'center' },
  lateDotUrgent: { backgroundColor: colors.unsafe },
  lateLine: { flex: 1, width: 3, backgroundColor: colors.rope, marginVertical: 2, minHeight: 10 },
  lateBody: { flex: 1, paddingBottom: 14 },
  lateWhen: { fontSize: 16, fontWeight: '900', color: colors.ink },
  lateText: { fontSize: 15, color: colors.ink, lineHeight: 21 },
  lateFooter: { fontSize: 14, color: colors.inkSoft, lineHeight: 20 },

  stat: { flex: 1, alignItems: 'center' },
  statLabel: { fontSize: 13, fontWeight: '700', opacity: 0.9 },
  statValue: { fontSize: 26, fontWeight: '900' },

  advice: { borderRadius: 6, padding: 16, gap: 10 },
  adviceHead: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  adviceTitle: { fontSize: 13, fontWeight: '800', letterSpacing: 0.5, textTransform: 'uppercase' },
  adviceShort: { fontSize: 22, fontWeight: '900', lineHeight: 27 },
  adviceRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  adviceText: { flex: 1, fontSize: 16, fontWeight: '700', lineHeight: 22 },
  adviceSource: { fontSize: 12, fontWeight: '600', opacity: 0.85 },

  info: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  infoBody: { flex: 1 },
  infoTitle: { fontSize: 13, fontWeight: '700', color: colors.inkSoft },
  infoText: { fontSize: 16, fontWeight: '700', lineHeight: 22 },
});
