import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { Translate } from '../i18n';
import { useApp } from '../lib/store';
import { BOAT_TYPES, TOUCH, boatIcon, colors, display } from '../lib/theme';
import { Glyph, WaveRule } from './art';
import type { BoatType } from '../lib/types';

export function Screen({
  title,
  onTitleLongPress,
  children,
  scroll = true,
}: {
  title: string;
  onTitleLongPress?: () => void;
  children: React.ReactNode;
  scroll?: boolean;
}) {
  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <Pressable onLongPress={onTitleLongPress} delayLongPress={800} disabled={!onTitleLongPress}>
        <View style={styles.titleWrap}>
          <Text style={[styles.title, display]}>{title}</Text>
          <WaveRule color={colors.sea} />
        </View>
      </Pressable>
      {scroll ? (
        <ScrollView contentContainerStyle={styles.scrollBody} keyboardShouldPersistTaps="handled">
          {children}
          <Disclaimer />
        </ScrollView>
      ) : (
        <View style={styles.fixedBody}>{children}</View>
      )}
    </SafeAreaView>
  );
}

/** Required on every safety screen. */
export function Disclaimer() {
  const { t } = useApp();
  return <Text style={styles.disclaimer}>{t('disclaimer')}</Text>;
}

export function Card({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return <Text style={styles.section}>{children}</Text>;
}

export function BigButton({
  label,
  icon,
  onPress,
  color = colors.sea,
  textColor = colors.white,
  disabled,
  busy,
  style,
}: {
  label: string;
  icon?: string;
  onPress: () => void;
  color?: string;
  textColor?: string;
  disabled?: boolean;
  busy?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || busy}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [
        styles.bigButton,
        { backgroundColor: color, opacity: disabled ? 0.45 : pressed ? 0.8 : 1 },
        style,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={textColor} />
      ) : (
        <View style={styles.bigButtonRow}>
          {icon ? <Glyph glyph={icon} size={26} color={textColor} /> : null}
          <Text style={[styles.bigButtonText, { color: textColor }]}>{label}</Text>
        </View>
      )}
    </Pressable>
  );
}

export function Banner({ text, tone = 'info', icon }: { text: string; tone?: 'info' | 'warn' | 'danger'; icon?: string }) {
  const bg = tone === 'danger' ? colors.unsafe : tone === 'warn' ? colors.caution : colors.inkSoft;
  const fg = tone === 'warn' ? colors.ink : colors.white;
  return (
    <View style={[styles.banner, { backgroundColor: bg }]}>
      {icon ? (
        <View style={styles.bannerIcon}>
          <Glyph glyph={icon} size={24} color={fg} />
        </View>
      ) : null}
      <Text style={[styles.bannerText, { color: fg }]}>{text}</Text>
    </View>
  );
}

export function Field(props: TextInputProps & { label: string }) {
  const { label, style, ...rest } = props;
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        placeholderTextColor={colors.inkSoft}
        accessibilityLabel={label}
        {...rest}
        style={[styles.input, style]}
      />
    </View>
  );
}

export function BoatPicker({
  value,
  onChange,
  labels,
}: {
  value: BoatType;
  onChange: (boat: BoatType) => void;
  /** Translator to use before a profile exists (onboarding). */
  labels?: Translate;
}) {
  const app = useApp();
  const t = labels ?? app.t;
  return (
    <View style={styles.boatRow}>
      {BOAT_TYPES.map((boat) => {
        const selected = boat === value;
        return (
          <Pressable
            key={boat}
            onPress={() => onChange(boat)}
            accessibilityRole="radio"
            accessibilityState={{ selected }}
            accessibilityLabel={t(`boat_${boat}`)}
            style={[styles.boatCard, selected && styles.boatCardSelected]}
          >
            <Text style={styles.boatIcon}>{boatIcon[boat]}</Text>
            <Text style={[styles.boatName, selected && styles.boatNameSelected]}>{t(`boat_${boat}`)}</Text>
            <Text style={[styles.boatHint, selected && styles.boatNameSelected]}>{t(`boat_${boat}_hint`)}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Choice({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      style={[styles.choice, selected && styles.choiceSelected]}
    >
      <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  screen: { flex: 1, backgroundColor: colors.bg },
  titleWrap: { paddingHorizontal: 16, paddingTop: 10, paddingBottom: 10, gap: 2 },
  title: { fontSize: 32, lineHeight: 38, fontWeight: '900', color: colors.ink, letterSpacing: 0.3 },
  scrollBody: { paddingHorizontal: 16, paddingBottom: 150, gap: 14 },
  fixedBody: { flex: 1, paddingHorizontal: 16, gap: 10 },
  disclaimer: { fontSize: 13, lineHeight: 18, color: colors.inkSoft, textAlign: 'center', marginTop: 6 },
  card: { backgroundColor: colors.card, borderRadius: 6, padding: 16, borderTopWidth: 3, borderTopColor: colors.ink },
  section: { fontSize: 20, fontWeight: '800', color: colors.ink, marginBottom: 10 },
  bigButton: {
    minHeight: TOUCH + 8,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
  },
  bigButtonRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10 },
  bigButtonText: { fontSize: 20, fontWeight: '800', textAlign: 'center', flexShrink: 1 },
  banner: { borderRadius: 6, paddingHorizontal: 14, paddingVertical: 12, flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  bannerIcon: { marginTop: 1 },
  bannerText: { fontSize: 16, fontWeight: '700', lineHeight: 23, flex: 1 },
  field: { marginBottom: 12 },
  fieldLabel: { fontSize: 15, fontWeight: '600', color: colors.ink, marginBottom: 6 },
  input: {
    minHeight: TOUCH,
    borderWidth: 2,
    borderColor: colors.line,
    borderRadius: 4,
    paddingHorizontal: 14,
    fontSize: 18,
    color: colors.ink,
    backgroundColor: colors.white,
  },
  boatRow: { flexDirection: 'row', gap: 8 },
  boatCard: {
    flex: 1,
    minHeight: 132,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: colors.ink,
    backgroundColor: colors.white,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 8,
  },
  boatCardSelected: { borderColor: colors.sea, backgroundColor: colors.sea },
  boatIcon: { fontSize: 40 },
  boatName: { fontSize: 15, fontWeight: '800', color: colors.ink, textAlign: 'center', marginTop: 6 },
  boatHint: { fontSize: 12, color: colors.inkSoft, textAlign: 'center', marginTop: 2 },
  boatNameSelected: { color: colors.white },
  choice: {
    minHeight: TOUCH,
    paddingHorizontal: 16,
    borderRadius: 4,
    borderWidth: 2,
    borderColor: colors.ink,
    backgroundColor: colors.white,
    alignItems: 'center',
    justifyContent: 'center',
  },
  choiceSelected: { borderColor: colors.sea, backgroundColor: colors.sea },
  choiceText: { fontSize: 16, fontWeight: '700', color: colors.ink },
  choiceTextSelected: { color: colors.white },
});
