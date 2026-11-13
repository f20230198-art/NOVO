import React, { useEffect, useState } from 'react';
import { Animated, PanResponder, Pressable, ScrollView, StyleSheet, View, type LayoutChangeEvent } from 'react-native';

import { colors } from '../lib/theme';

type Props = {
  /** Always visible: the verdict. Dragging or tapping it opens the sheet. */
  peek: React.ReactNode;
  /** Shown when the sheet is pulled up. */
  children: React.ReactNode;
  /** Height of the open sheet, in dp (the parent's height minus room for the header). */
  openHeight: number;
  /** Reports the visible height of the closed sheet, so the map can keep its credits above it. */
  onPeekHeight?: (h: number) => void;
  onOpenChange?: (open: boolean) => void;
  /** Screen-reader labels for the handle, already translated. */
  openLabel: string;
  closeLabel: string;
};

const SPRING = { useNativeDriver: true, damping: 26, stiffness: 260, mass: 0.9 } as const;

/** The sheet's position and gestures: a plain object with its own closure state. */
function makeSheet(initialClosed: number, setOpen: (open: boolean) => void) {
  const y = new Animated.Value(initialClosed);
  let base = initialClosed; // where the sheet rests now
  let closed = initialClosed; // resting position when closed
  let open = false;
  let onChange: ((open: boolean) => void) | undefined;

  const snap = (toOpen: boolean, velocity = 0) => {
    open = toOpen;
    base = toOpen ? 0 : closed;
    setOpen(toOpen);
    onChange?.(toOpen);
    Animated.spring(y, { ...SPRING, toValue: base, velocity }).start();
  };

  const pan = PanResponder.create({
    // Let taps through to the buttons in the peek; only take over once the finger moves.
    onMoveShouldSetPanResponder: (_e, d) => Math.abs(d.dy) > 6 && Math.abs(d.dy) > Math.abs(d.dx),
    onPanResponderGrant: () => y.stopAnimation(),
    onPanResponderMove: (_e, d) => y.setValue(Math.min(closed + 40, Math.max(-20, base + d.dy))),
    // A flick decides; otherwise whichever position is nearer.
    onPanResponderRelease: (_e, d) => snap(d.vy < -0.5 ? true : d.vy > 0.5 ? false : base + d.dy < closed / 2, d.vy),
    onPanResponderTerminate: () => snap(open),
  });

  return {
    y,
    pan,
    snap,
    setOnChange: (fn: typeof onChange) => {
      onChange = fn;
    },
    setClosed: (value: number) => {
      closed = value;
      if (!open) {
        base = value;
        Animated.spring(y, { ...SPRING, toValue: value }).start();
      }
    },
  };
}

/**
 * A two-position bottom sheet over the map, built on Animated + PanResponder (both in Expo Go,
 * no native module). The sheet is always its full open height and only slides, on the native
 * driver, so opening it never re-lays-out the screen.
 */
export function MapSheet({ peek, children, openHeight, onPeekHeight, onOpenChange, openLabel, closeLabel }: Props) {
  const [peekHeight, setPeekHeight] = useState(150);
  const [open, setOpen] = useState(false);
  const closedY = Math.max(0, openHeight - peekHeight);
  // Made once; it keeps its own gesture state, so nothing mutable is read while rendering.
  const [sheet] = useState(() => makeSheet(closedY, setOpen));
  const { y, pan, snap } = sheet;

  useEffect(() => sheet.setOnChange(onOpenChange), [sheet, onOpenChange]);
  // Keep the closed position right when the peek content changes height (e.g. skeleton → verdict).
  useEffect(() => sheet.setClosed(closedY), [sheet, closedY]);

  const onPeekLayout = (e: LayoutChangeEvent) => {
    const h = Math.round(e.nativeEvent.layout.height) + HANDLE;
    if (Math.abs(h - peekHeight) > 1) {
      setPeekHeight(h);
      onPeekHeight?.(h);
    }
  };

  return (
    <Animated.View style={[styles.sheet, { height: openHeight, transform: [{ translateY: y }] }]}>
      <View {...pan.panHandlers}>
        <Pressable
          onPress={() => snap(!open)}
          accessibilityRole="button"
          accessibilityLabel={open ? closeLabel : openLabel}
          style={styles.handleHit}
        >
          <View style={styles.handle} />
        </Pressable>
        <View onLayout={onPeekLayout}>{peek}</View>
      </View>
      <ScrollView
        style={styles.flex}
        contentContainerStyle={styles.body}
        keyboardShouldPersistTaps="handled"
        scrollEnabled={open}
        showsVerticalScrollIndicator={false}
      >
        {children}
      </ScrollView>
    </Animated.View>
  );
}

const HANDLE = 22;

const styles = StyleSheet.create({
  flex: { flex: 1 },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.card,
    borderTopLeftRadius: 14,
    borderTopRightRadius: 14,
    borderTopWidth: 2,
    borderColor: colors.ink,
    elevation: 16,
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: -3 },
  },
  handleHit: { height: HANDLE, alignItems: 'center', justifyContent: 'center' },
  handle: { width: 44, height: 5, borderRadius: 3, backgroundColor: colors.line },
  // Room at the bottom for the floating SOS button.
  body: { paddingHorizontal: 16, paddingTop: 6, paddingBottom: 130, gap: 14 },
});
