import React, { useState } from 'react';
import { LayoutAnimation, Pressable, StyleSheet, Text, View } from 'react-native';

import { num } from '../../lib/format';
import { useApp } from '../../lib/store';
import { TOUCH, colors, display, levelColor, levelInk } from '../../lib/theme';
import type { HarbourMouth, HourRisk, Level } from '../../lib/types';
import { Icon, LevelMark } from '../art';
import { HOUR } from './plan';
import { clock, compass, kmh, metres } from './words';

type MouthHour = HarbourMouth['hourly'][number];

const MOUTH_WORD: Record<Level, 'mouthCalm' | 'mouthRough' | 'mouthDangerous'> = {
  SAFE: 'mouthCalm',
  CAUTION: 'mouthRough',
  UNSAFE: 'mouthDangerous',
};

/**
 * Every hour of the chosen day, one row each: the server's level, waves, wind with an arrow
 * showing where it blows to, current, and the harbour-mouth estimate. Tap a row to leave or be
 * back at that hour. Levels and reasons are shown as the server sent them.
 */
export function HourList({
  hours,
  mouth,
  departAt,
  returnAt,
  now,
  onLeave,
  onBack,
}: {
  hours: HourRisk[];
  mouth: MouthHour[];
  departAt: number;
  returnAt: number;
  now: number;
  onLeave: (ms: number) => void;
  onBack: (ms: number) => void;
}) {
  const { t } = useApp();
  const [open, setOpen] = useState<string | null>(null);

  const toggle = (time: string) => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setOpen((o) => (o === time ? null : time));
  };

  return (
    <View style={styles.list}>
      {hours.map((h) => {
        const start = new Date(h.time).getTime();
        const end = start + HOUR;
        const atSea = end > departAt && start < returnAt;
        const isOpen = open === h.time;
        const m = mouth.find((x) => x.time === h.time);
        const leaveAt = Math.max(start, now);
        const why = h.level !== 'SAFE' ? h.reasons[0]?.text : null; // server text, in the fisher's language
        const time = clock(t, new Date(start));
        const waves = metres(t, num(h.wave_height));
        const wind = kmh(t, num(h.wind_speed, 0));
        const dir = h.wind_from ? t('windFrom', { dir: compass(t, h.wind_from) }) : '';
        return (
          <View key={h.time} style={[styles.row, atSea && styles.rowAtSea]}>
            <Pressable
              onPress={() => toggle(h.time)}
              accessibilityRole="button"
              accessibilityState={{ expanded: isOpen }}
              accessibilityLabel={t('hourA11y', { time, level: t(h.level), waves, wind, dir })}
              style={({ pressed }) => [styles.rowMain, pressed && styles.pressed]}
            >
              <View style={[styles.levelCol, { backgroundColor: levelColor[h.level] }]}>
                <Text style={[styles.hourText, display, { color: levelInk[h.level] }]} numberOfLines={2} adjustsFontSizeToFit>
                  {time}
                </Text>
                <LevelMark level={h.level} size={22} color={levelInk[h.level]} ground={levelColor[h.level]} />
              </View>
              <View style={styles.body}>
                <View style={styles.line}>
                  <Icon name="wave" size={18} color={colors.inkSoft} />
                  <Text style={styles.value}>{waves}</Text>
                  <Icon name="wind" size={18} color={colors.inkSoft} />
                  <Text style={styles.value}>{wind}</Text>
                  {h.wind_from_deg != null ? (
                    // The arrow points where the wind blows to (from + 180°).
                    <Icon name="arrow" size={18} color={colors.ink} rotate={(h.wind_from_deg + 180) % 360} weight={2.6} />
                  ) : null}
                  {h.wind_from ? <Text style={styles.small}>{compass(t, h.wind_from)}</Text> : null}
                </View>
                {h.current_speed != null || m ? (
                  <View style={styles.line}>
                    {h.current_speed != null ? (
                      <>
                        <Icon name="compass" size={16} color={colors.inkSoft} />
                        <Text style={styles.small} accessibilityLabel={`${t('current')} ${kmh(t, num(h.current_speed))}`}>
                          {kmh(t, num(h.current_speed))}
                        </Text>
                        {h.current_to_deg != null ? (
                          <Icon name="arrow" size={16} color={colors.inkSoft} rotate={h.current_to_deg} />
                        ) : null}
                      </>
                    ) : null}
                    {m ? (
                      <View style={[styles.mouth, { borderColor: levelColor[m.level] }]}>
                        <Icon name="anchor" size={14} color={colors.ink} />
                        <Text style={styles.mouthText}>{t(MOUTH_WORD[m.level])}</Text>
                      </View>
                    ) : null}
                  </View>
                ) : null}
                {why ? (
                  <Text style={styles.why} numberOfLines={isOpen ? undefined : 1}>
                    {why}
                  </Text>
                ) : null}
              </View>
              <Icon name={isOpen ? 'chevUp' : 'chevDown'} size={20} color={colors.inkSoft} />
            </Pressable>
            {isOpen ? (
              <View style={styles.actions}>
                <Pressable
                  onPress={() => {
                    onLeave(leaveAt);
                    setOpen(null);
                  }}
                  accessibilityRole="button"
                  style={({ pressed }) => [styles.action, pressed && styles.pressed]}
                >
                  <Icon name="sail" size={20} color={colors.white} />
                  <Text style={styles.actionText}>
                    {t('leaveAtHour', { time: leaveAt <= now + 60000 ? t('now') : clock(t, new Date(leaveAt)) })}
                  </Text>
                </Pressable>
                <Pressable
                  onPress={() => {
                    onBack(start);
                    setOpen(null);
                  }}
                  disabled={start <= departAt}
                  accessibilityRole="button"
                  style={({ pressed }) => [styles.action, styles.actionBack, { opacity: start <= departAt ? 0.4 : pressed ? 0.75 : 1 }]}
                >
                  <Icon name="back" size={20} color={colors.white} />
                  <Text style={styles.actionText}>{t('backByHour', { time })}</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  pressed: { opacity: 0.75 },
  list: { gap: 6 },
  row: { borderRadius: 6, borderWidth: 2, borderColor: colors.line, backgroundColor: colors.card, overflow: 'hidden' },
  rowAtSea: { borderColor: colors.sea },
  rowMain: { flexDirection: 'row', alignItems: 'center', minHeight: TOUCH + 12, paddingRight: 10, gap: 10 },
  levelCol: { width: 84, alignSelf: 'stretch', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 8, paddingHorizontal: 4 },
  hourText: { fontSize: 16, fontWeight: '900', textAlign: 'center' },
  body: { flex: 1, gap: 4, paddingVertical: 8 },
  line: { flexDirection: 'row', alignItems: 'center', gap: 4, flexWrap: 'wrap' },
  value: { fontSize: 16, fontWeight: '800', color: colors.ink, marginRight: 4 },
  small: { fontSize: 13, fontWeight: '600', color: colors.inkSoft },
  mouth: { flexDirection: 'row', alignItems: 'center', gap: 3, borderWidth: 2, borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1, marginLeft: 4 },
  mouthText: { fontSize: 12, lineHeight: 17, fontWeight: '800', color: colors.ink },
  why: { fontSize: 13, color: colors.ink, lineHeight: 20 },
  actions: { flexDirection: 'row', gap: 8, padding: 8, paddingTop: 0 },
  action: {
    flex: 1,
    minHeight: TOUCH,
    borderRadius: 6,
    backgroundColor: colors.safe,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingHorizontal: 8,
  },
  actionBack: { backgroundColor: colors.sea },
  actionText: { fontSize: 15, fontWeight: '800', color: colors.white, flexShrink: 1 },
});
