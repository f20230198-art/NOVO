import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, G, Line, Path, Rect } from 'react-native-svg';

import type { Level } from '../lib/types';

/**
 * One drawn icon family: 24 px grid, round 2.2 px stroke, no fills. These replace emoji so
 * the app looks the same on every phone and reads as one hand.
 */
const ICONS = {
  boat: ['M3 14h18l-2.5 5h-13L3 14z', 'M12 14V4', 'M12 5l6 7h-6'],
  mic: ['M9 6a3 3 0 016 0v5a3 3 0 01-6 0V6z', 'M5 11a7 7 0 0014 0', 'M12 18v3'],
  sail: ['M12 3v13', 'M12 4c5 3 7 7 7 11h-7', 'M12 8c-3 2-4.5 4.5-5 7h5', 'M3 20c2 1.4 4 1.4 6 0s4-1.4 6 0 4 1.4 6 0'],
  people: ['M6 8a3 3 0 106 0 3 3 0 00-6 0z', 'M3 20c0-3.5 2.7-6 6-6s6 2.5 6 6', 'M15 6.6a2.6 2.6 0 110 5', 'M17 14.4c2.4.6 4 2.7 4 5.6'],
  flag: ['M5 21V4', 'M5 5h12l-2.5 4 2.5 4H5'],
  person: ['M8 8a4 4 0 108 0 4 4 0 00-8 0z', 'M4 21c0-4.2 3.6-7 8-7s8 2.8 8 7'],
  wave: ['M2 9c2.5-3 5-3 7.5 0s5 3 7.5 0 3.5-2 5-1', 'M2 16c2.5-3 5-3 7.5 0s5 3 7.5 0 3.5-2 5-1'],
  wind: ['M3 9h11a3 3 0 10-3-3', 'M3 15h15a3 3 0 11-3 3', 'M3 12h6'],
  clock: ['M3 12a9 9 0 1018 0 9 9 0 00-18 0z', 'M12 7v5l3.5 2'],
  back: ['M8 5l-4 4 4 4', 'M4 9h10a5 5 0 010 10h-4'],
  check: ['M4 12.5l5.5 5.5L20 6.5'],
  alert: ['M12 3.5l9.5 17h-19L12 3.5z', 'M12 10v5', 'M12 17.6v.3'],
  cross: ['M6 6l12 12', 'M18 6L6 18'],
  lifebuoy: ['M3 12a9 9 0 1018 0 9 9 0 00-18 0z', 'M8.5 12a3.5 3.5 0 107 0 3.5 3.5 0 00-7 0z', 'M5.6 5.6l3.9 3.9', 'M14.5 14.5l3.9 3.9', 'M18.4 5.6l-3.9 3.9', 'M9.5 14.5l-3.9 3.9'],
  anchor: ['M10 5a2 2 0 104 0 2 2 0 00-4 0z', 'M12 7v14', 'M8 11h8', 'M4 14c0 4 3.5 7 8 7s8-3 8-7'],
  pin: ['M12 21s7-6.2 7-11.5a7 7 0 00-14 0C5 14.8 12 21 12 21z', 'M9.5 9.5a2.5 2.5 0 105 0 2.5 2.5 0 00-5 0z'],
  refresh: ['M20 11a8 8 0 10-2.3 6.3', 'M20 5v6h-6'],
  speaker: ['M4 9.5v5h3.5L12 18V6L7.5 9.5H4z', 'M15.5 9a4 4 0 010 6', 'M18 6.5a7.5 7.5 0 010 11'],
  chevDown: ['M6 9l6 6 6-6'],
  chevUp: ['M6 15l6-6 6 6'],
  chevRight: ['M9 6l6 6-6 6'],
  send: ['M4 12l16-8-6 16-2.5-6.5L4 12z'],
  timer: ['M4 13a8 8 0 1016 0 8 8 0 00-16 0z', 'M12 9v4', 'M9 2.5h6'],
  house: ['M3 11l9-7 9 7', 'M5.5 10v10h13V10'],
  offline: ['M3 3l18 18', 'M5 12.5a10 10 0 014-2.4', 'M13 10a10 10 0 016 2.5', 'M8.5 16a5 5 0 017 0'],
  message: ['M4 5h16v11H9l-5 4V5z'],
  question: ['M3 12a9 9 0 1018 0 9 9 0 00-18 0z', 'M9.5 9.5a2.5 2.5 0 115 0c0 1.7-2.5 2-2.5 4', 'M12 16.8v.3'],
  play: ['M7 5l12 7-12 7V5z'],
  compass: ['M3 12a9 9 0 1018 0 9 9 0 00-18 0z', 'M15.5 8.5l-2 5-5 2 2-5 5-2z'],
  depth: ['M3 6c2-1.5 4-1.5 6 0s4 1.5 6 0 4-1.5 6 0', 'M12 10v9', 'M8.5 15.5L12 19l3.5-3.5'],
  tide: ['M3 17c2-1.5 4-1.5 6 0s4 1.5 6 0 4-1.5 6 0', 'M12 13V4', 'M8.5 7.5L12 4l3.5 3.5'],
  arrow: ['M12 20V5', 'M6 11l6-6 6 6'],
  plus: ['M12 5v14', 'M5 12h14'],
} as const;

export type IconName = keyof typeof ICONS;

/** Emoji used in older call sites, mapped to the drawn family. */
const EMOJI: Record<string, IconName> = {
  '⛵': 'sail', '🏠': 'house', '⏱': 'timer', '🔄': 'refresh', '🔊': 'speaker', '▲': 'chevUp', '▼': 'chevDown',
  '⚠': 'alert', '⚠️': 'alert', '✔': 'check', '🚨': 'alert', '🆘': 'lifebuoy', '📴': 'offline', '⏳': 'clock',
  '🎬': 'play', '📩': 'message', '❓': 'question', '🎤': 'mic', '🎙': 'mic', '📍': 'pin', '🌊': 'wave',
  '💨': 'wind', '↩': 'back', '🕓': 'clock', '👥': 'people', '👤': 'person', '✖': 'cross', '➤': 'send', '⚓': 'anchor',
};

export function iconFor(glyph: string | undefined): IconName | null {
  if (!glyph) return null;
  if (glyph in ICONS) return glyph as IconName;
  return EMOJI[glyph] ?? null;
}

export function Icon({
  name,
  size = 24,
  color = '#14212B',
  weight = 2.2,
  rotate = 0,
}: {
  name: IconName;
  size?: number;
  color?: string;
  weight?: number;
  rotate?: number;
}) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <G rotation={rotate} origin="12, 12">
        {ICONS[name].map((d) => (
          <Path key={d} d={d} stroke={color} strokeWidth={weight} strokeLinecap="round" strokeLinejoin="round" />
        ))}
      </G>
    </Svg>
  );
}

/** Icon when the glyph is known, otherwise the glyph as text (keeps unknown emoji working). */
export function Glyph({ glyph, size = 22, color }: { glyph: string; size?: number; color: string }) {
  const name = iconFor(glyph);
  if (name) return <Icon name={name} size={size} color={color} />;
  return <Text style={{ fontSize: size - 4, color }}>{glyph}</Text>;
}

/** The level mark: tick, warning triangle or cross inside a disc. Shape carries the meaning. */
export function LevelMark({ level, size = 28, color, ground }: { level: Level; size?: number; color: string; ground: string }) {
  const name: IconName = level === 'SAFE' ? 'check' : level === 'CAUTION' ? 'alert' : 'cross';
  return (
    <View style={[styles.mark, { width: size, height: size, borderRadius: size / 2, backgroundColor: color }]}>
      <Icon name={name} size={size * 0.62} color={ground} weight={3} />
    </View>
  );
}

function swell(y: number, amp: number, width = 360, step = 30, phase = 0): string {
  let d = `M${-step + phase} ${y}`;
  for (let x = -step + phase; x < width + step; x += step) {
    d += ` q${step / 2} ${-amp} ${step} 0`;
  }
  return d;
}

/** A Kerala vallam: long plank canoe with a raised prow and stern, and a small lateen sail. */
function Vallam({ x, y, tilt = 0, color, sail = true }: { x: number; y: number; tilt?: number; color: string; sail?: boolean }) {
  return (
    <G x={x} y={y} rotation={tilt}>
      <Path d="M-58 -11 Q-53 -2 -40 6 H38 Q51 0 60 -15 Q45 -4 30 -3 H-34 Q-47 -4 -58 -11 Z" fill={color} />
      {sail ? (
        <>
          <Path d="M-6 -3 V-47" stroke={color} strokeWidth={2.6} strokeLinecap="round" />
          <Path d="M-4 -45 Q24 -33 29 -8 H-4 Z" fill={color} fillOpacity={0.82} />
          <Path d="M-8 -40 Q-22 -27 -24 -8 H-8 Z" fill={color} fillOpacity={0.5} />
        </>
      ) : (
        <Path d="M-6 -3 V-30" stroke={color} strokeWidth={2.6} strokeLinecap="round" />
      )}
      {/* the fisher, sitting aft */}
      <Circle cx={-34} cy={-13} r={4} fill={color} />
      <Path d="M-38 -3 Q-34 -11 -30 -3 Z" fill={color} />
    </G>
  );
}

/**
 * The picture behind the verdict. It says the same thing as the word, for someone who
 * does not read it: a boat sailing on a flat sea at sunrise, a boat pitching in a chop,
 * or a boat pulled up on the sand while the sea breaks.
 */
export function SeaScene({ level, ink, height = 132 }: { level: Level; ink: string; height?: number }) {
  return (
    <View style={{ height }} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Svg width="100%" height={height} viewBox="0 0 360 132" preserveAspectRatio="xMidYMax slice">
        {level === 'SAFE' ? (
          <>
            {/* sun coming up over the water */}
            <Circle cx={270} cy={86} r={30} fill={ink} fillOpacity={0.2} />
            {[200, 222, 245, 270, 295, 318, 340].map((x, i) => (
              <Line key={x} x1={270 + (x - 270) * 0.62} y1={86 - Math.cos((i - 3) / 2.4) * 38} x2={270 + (x - 270) * 0.86}
                y2={86 - Math.cos((i - 3) / 2.4) * 54} stroke={ink} strokeOpacity={0.28} strokeWidth={3} strokeLinecap="round" />
            ))}
            <Path d="M34 30 q7 -8 14 0 q7 -8 14 0" stroke={ink} strokeOpacity={0.5} strokeWidth={2.4} strokeLinecap="round" fill="none" />
            <Path d="M78 46 q5 -6 10 0 q5 -6 10 0" stroke={ink} strokeOpacity={0.36} strokeWidth={2.2} strokeLinecap="round" fill="none" />
            <Rect x={0} y={90} width={360} height={42} fill={ink} fillOpacity={0.1} />
            <Vallam x={128} y={92} tilt={-2} color={ink} />
            <Path d={swell(100, 4)} stroke={ink} strokeOpacity={0.55} strokeWidth={2.6} strokeLinecap="round" fill="none" />
            <Path d={swell(113, 4, 360, 30, 12)} stroke={ink} strokeOpacity={0.34} strokeWidth={2.4} strokeLinecap="round" fill="none" />
            <Path d={swell(125, 3, 360, 30, 4)} stroke={ink} strokeOpacity={0.22} strokeWidth={2.2} strokeLinecap="round" fill="none" />
          </>
        ) : null}
        {level === 'CAUTION' ? (
          <>
            {/* cloud bank and a boat working in a chop */}
            <Path d="M214 44 q4 -20 26 -17 q10 -17 30 -7 q22 -5 24 15 q16 3 13 16 H206 q-8 -9 8 -7 Z" fill={ink} fillOpacity={0.16} />
            <Path d="M40 36 q3 -13 17 -11 q8 -11 20 -3 q14 -2 14 10 H36 q-3 -6 4 4 Z" fill={ink} fillOpacity={0.12} />
            <Rect x={0} y={92} width={360} height={40} fill={ink} fillOpacity={0.1} />
            <Vallam x={150} y={88} tilt={-11} color={ink} />
            <Path d={swell(98, 10, 360, 36)} stroke={ink} strokeOpacity={0.6} strokeWidth={2.8} strokeLinecap="round" fill="none" />
            <Path d={swell(112, 9, 360, 36, 16)} stroke={ink} strokeOpacity={0.4} strokeWidth={2.6} strokeLinecap="round" fill="none" />
            <Path d={swell(126, 7, 360, 36, 6)} stroke={ink} strokeOpacity={0.26} strokeWidth={2.4} strokeLinecap="round" fill="none" />
          </>
        ) : null}
        {level === 'UNSAFE' ? (
          <>
            {/* breakers, rain, and the boat pulled up on the sand */}
            {[150, 176, 204, 232, 260, 290, 318, 344].map((x, i) => (
              <Line key={x} x1={x} y1={6 + (i % 3) * 7} x2={x - 9} y2={30 + (i % 3) * 7} stroke={ink} strokeOpacity={0.3} strokeWidth={2.2} strokeLinecap="round" />
            ))}
            <Path d="M150 96 C168 50 214 38 238 62 C222 58 206 68 210 86 C222 66 250 70 252 96 Z" fill={ink} fillOpacity={0.28} />
            <Path d="M236 100 C254 58 300 48 324 72 C308 68 292 78 296 94 C308 76 336 80 338 104 Z" fill={ink} fillOpacity={0.2} />
            <Path d={swell(102, 13, 360, 44, 130)} stroke={ink} strokeOpacity={0.6} strokeWidth={3} strokeLinecap="round" fill="none" />
            <Path d={swell(118, 11, 360, 44, 150)} stroke={ink} strokeOpacity={0.4} strokeWidth={2.8} strokeLinecap="round" fill="none" />
            <Path d="M0 132 V104 Q60 92 150 112 Q170 120 176 132 Z" fill={ink} fillOpacity={0.24} />
            <Vallam x={72} y={100} tilt={7} color={ink} sail={false} />
            <Path d="M22 112 L44 102" stroke={ink} strokeOpacity={0.7} strokeWidth={2.4} strokeLinecap="round" />
          </>
        ) : null}
      </Svg>
    </View>
  );
}

/** Small rope-and-wave rule used between sections instead of another card border. */
export function WaveRule({ color, width = 72 }: { color: string; width?: number }) {
  return (
    <Svg width={width} height={10} viewBox={`0 0 ${width} 10`}>
      <Path d={swell(6, 3.2, width, 12)} stroke={color} strokeWidth={2} strokeLinecap="round" fill="none" />
    </Svg>
  );
}

const styles = StyleSheet.create({
  mark: { alignItems: 'center', justifyContent: 'center' },
});
