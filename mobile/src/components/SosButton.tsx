import React, { useEffect, useRef, useState } from 'react';
import { Animated, Easing, Pressable, StyleSheet, Text, Vibration, View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';

import { callCoastGuard, sendSos } from '../lib/sos';
import { useApp } from '../lib/store';
import { colors } from '../lib/theme';

const HOLD_MS = 2000;
const SIZE = 84;
const STROKE = 6;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

/**
 * Floating SOS button. Hold for 2 seconds: the ring fills, then the SMS composer
 * opens with the location. Releasing early cancels.
 */
export function SosButton({ bottom = 96 }: { bottom?: number }) {
  const { profile, contacts, trip, t } = useApp();
  const progress = useRef(new Animated.Value(0)).current;
  const [holding, setHolding] = useState(false);
  // After an SOS, a one-tap call to the Coast Guard stays on screen.
  const [showCall, setShowCall] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const messageTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (messageTimer.current) clearTimeout(messageTimer.current);
    },
    [],
  );

  if (!profile) return null;

  const flash = (text: string, ms = 5000) => {
    setMessage(text);
    if (messageTimer.current) clearTimeout(messageTimer.current);
    messageTimer.current = setTimeout(() => setMessage(null), ms);
  };

  const begin = () => {
    setHolding(true);
    setMessage(t('sosHold'));
    progress.setValue(0);
    Animated.timing(progress, {
      toValue: 1,
      duration: HOLD_MS,
      easing: Easing.linear,
      useNativeDriver: false,
    }).start(({ finished }) => {
      if (!finished) return;
      setHolding(false);
      progress.setValue(0);
      Vibration.vibrate([0, 300, 150, 300]);
      flash(t('sosSending'), 15000);
      setShowCall(true);
      sendSos(profile, contacts, t, trip).then((result) =>
        flash(result === 'opened' ? t('sosOpened') : result === 'no-contacts' ? t('sosNoContacts') : t('sosNoSms'), 12000),
      );
    });
  };

  const cancel = () => {
    if (!holding) return;
    progress.stopAnimation();
    progress.setValue(0);
    setHolding(false);
    flash(t('sosHold'), 2500);
  };

  const dashOffset = progress.interpolate({ inputRange: [0, 1], outputRange: [CIRCUMFERENCE, 0] });

  return (
    <View pointerEvents="box-none" style={[styles.wrap, { bottom }]}>
      {message ? (
        <View style={styles.bubble}>
          <Text style={styles.bubbleText}>{message}</Text>
        </View>
      ) : null}
      {showCall ? (
        <Pressable onPress={callCoastGuard} accessibilityRole="button" accessibilityLabel={t('callCoastGuard')} style={styles.call}>
          <Text style={styles.callText}>📞 {t('callCoastGuard')}</Text>
        </Pressable>
      ) : null}
      <Pressable
        onPressIn={begin}
        onPressOut={cancel}
        accessibilityRole="button"
        accessibilityLabel={`${t('sos')}. ${t('sosHold')}`}
        style={styles.button}
      >
        <Svg width={SIZE} height={SIZE} style={styles.ring}>
          <Circle cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} stroke="rgba(255,255,255,0.35)" strokeWidth={STROKE} fill="none" />
          <AnimatedCircle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            stroke={colors.white}
            strokeWidth={STROKE}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={`${CIRCUMFERENCE} ${CIRCUMFERENCE}`}
            strokeDashoffset={dashOffset}
            rotation={-90}
            origin={`${SIZE / 2}, ${SIZE / 2}`}
          />
        </Svg>
        <Text style={styles.label}>🆘</Text>
        <Text style={styles.text}>{t('sos')}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'absolute', right: 14, alignItems: 'flex-end' },
  bubble: {
    backgroundColor: colors.ink,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    marginBottom: 8,
    maxWidth: 240,
  },
  bubbleText: { color: colors.white, fontSize: 15, fontWeight: '700' },
  call: {
    backgroundColor: colors.white,
    borderColor: colors.unsafe,
    borderWidth: 3,
    borderRadius: 14,
    paddingHorizontal: 14,
    minHeight: 56,
    justifyContent: 'center',
    marginBottom: 8,
    elevation: 6,
  },
  callText: { color: colors.unsafe, fontSize: 18, fontWeight: '900' },
  button: {
    width: SIZE,
    height: SIZE,
    borderRadius: SIZE / 2,
    backgroundColor: colors.unsafe,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 8,
    shadowColor: '#000',
    shadowOpacity: 0.3,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 3 },
  },
  ring: { position: 'absolute', top: 0, left: 0 },
  label: { fontSize: 24 },
  text: { color: colors.white, fontSize: 15, fontWeight: '900', marginTop: -2 },
});
