import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, Vibration, View, type ScrollViewInstance } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { BigButton } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { formatClock } from '../lib/format';
import { notifyLocal } from '../lib/notifications';
import { loadJson, saveJson, useApp } from '../lib/store';
import { TOUCH, colors } from '../lib/theme';
import type { FamilyMessage, FamilyStatus } from '../lib/types';

const POLL_MS = 5000;
const LAST_SEEN_KEY = 'seasafe.family.lastNotified';
const URGENT_BUZZ = [0, 900, 300, 900, 300, 900];
const NORMAL_BUZZ = [0, 300];

function firstLink(text: string): string | null {
  const m = text.match(/https?:\/\/\S+/);
  return m ? m[0].replace(/[.,)]+$/, '') : null;
}

function timeLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date().toDateString() === d.toDateString();
  return today ? formatClock(d) : `${d.toDateString().slice(4, 10)} ${formatClock(d)}`;
}

export default function FamilyScreen() {
  const { family, setFamily, t } = useApp();
  const router = useRouter();
  const [status, setStatus] = useState<FamilyStatus | null>(family);
  const [messages, setMessages] = useState<FamilyMessage[]>([]);
  const [offline, setOffline] = useState(false);
  const lastId = useRef(0);
  const scrollRef = useRef<ScrollViewInstance>(null);

  useEffect(() => {
    if (!family) router.replace('/onboarding');
  }, [family, router]);

  const fisherName = status?.fisher.name || family?.fisher.name || '';

  const poll = useCallback(async () => {
    if (!family) return;
    try {
      const fresh = await api.familyMessages(lastId.current);
      setOffline(false);
      if (fresh.length) {
        lastId.current = fresh[fresh.length - 1].id;
        setMessages((prev) => [...prev, ...fresh.filter((m) => !prev.some((p) => p.id === m.id))]);
        // Notify for every message this phone has not shown yet, including ones that
        // arrived while the app was closed.
        const notified = (await loadJson<number>(LAST_SEEN_KEY)) ?? 0;
        const unseen = fresh.filter((m) => m.id > notified);
        if (unseen.length) {
          await saveJson(LAST_SEEN_KEY, unseen[unseen.length - 1].id);
          const urgent = unseen.some((m) => m.urgent);
          Vibration.vibrate(urgent ? URGENT_BUZZ : NORMAL_BUZZ);
          for (const m of unseen) void notifyLocal('Sea Safe', m.text);
        }
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        await setFamily(null);
        return;
      }
      setOffline(true);
    }
  }, [family, setFamily]);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await api.familyMe());
    } catch {
      // keep the last status
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void poll();
      void refreshStatus();
      const a = setInterval(poll, POLL_MS);
      const b = setInterval(refreshStatus, POLL_MS * 2);
      return () => {
        clearInterval(a);
        clearInterval(b);
      };
    }, [poll, refreshStatus]),
  );

  useEffect(() => {
    const id = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [messages.length]);

  if (!family) return null;

  // An SOS is "open" until a later all-clear or extension arrives.
  const lastSos = [...messages].reverse().find((m) => m.kind === 'sos' || m.kind === 'auto_sos');
  const resolved = lastSos && messages.some((m) => m.id > lastSos.id && (m.kind === 'all_clear' || m.kind === 'extended'));
  const openSos = lastSos && !resolved ? lastSos : null;
  const sosLink = openSos ? firstLink(openSos.text) : null;

  const trip = status?.trip;
  const tripState = !trip
    ? { text: t('statusUnknown'), color: colors.inkSoft }
    : trip.status === 'emergency'
      ? { text: t('statusEmergency'), color: colors.unsafe }
      : trip.status === 'overdue'
        ? { text: t('statusOverdue', { time: formatClock(new Date(trip.planned_return)) }), color: colors.unsafe }
        : trip.status === 'active'
          ? { text: t('statusAtSea', { time: formatClock(new Date(trip.planned_return)) }), color: colors.sea }
          : { text: t('statusHome'), color: colors.safe };

  const unlink = async () => {
    try {
      await api.familyUnlink();
    } catch {
      // unlinked on this phone anyway
    }
    await saveJson(LAST_SEEN_KEY, null);
    await setFamily(null);
  };

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <Text style={styles.brand}>🌊 Sea Safe · {t('familyTitle')}</Text>
        <Text style={styles.fisher}>{fisherName}</Text>
        {status?.fisher.home_name ? <Text style={styles.sub}>📍 {status.fisher.home_name}</Text> : null}
      </View>

      <View style={[styles.status, { backgroundColor: tripState.color }]}>
        <Text style={styles.statusText}>{tripState.text}</Text>
        {trip?.last_contact_at && trip.status !== 'returned' ? (
          <Text style={styles.statusSub}>{t('lastContact', { time: timeLabel(trip.last_contact_at) })}</Text>
        ) : null}
      </View>

      {openSos ? (
        <View style={styles.sos}>
          <Text style={styles.sosTitle}>🆘 {t('sosAlertTitle', { name: fisherName })}</Text>
          <Text style={styles.sosTime}>{timeLabel(openSos.created_at)}</Text>
          <View style={styles.sosButtons}>
            {sosLink ? (
              <BigButton label={t('openLocation')} icon="📍" onPress={() => Linking.openURL(sosLink)} color={colors.white} textColor={colors.unsafe} style={styles.flex} />
            ) : null}
            <BigButton label={t('callCoastGuard')} icon="📞" onPress={() => Linking.openURL('tel:1554')} color={colors.ink} style={styles.flex} />
          </View>
        </View>
      ) : null}

      <Text style={styles.threadTitle}>{t('messagesFrom')}</Text>
      {offline ? <Text style={styles.offline}>📴 {t('noConnection')}</Text> : null}
      <ScrollView ref={scrollRef} style={styles.flex} contentContainerStyle={styles.thread}>
        {messages.length === 0 ? <Text style={styles.empty}>{t('noFamilyMessages', { name: fisherName })}</Text> : null}
        {messages.map((m) => {
          const link = firstLink(m.text);
          return (
            <View key={m.id} style={[styles.bubble, m.urgent && styles.bubbleUrgent]}>
              <Text style={styles.sender}>Sea Safe</Text>
              <Text style={styles.msgText}>{m.text}</Text>
              <View style={styles.msgFoot}>
                {link ? (
                  <Pressable onPress={() => Linking.openURL(link)} hitSlop={8} accessibilityRole="link">
                    <Text style={styles.msgLink}>📍 {t('openLocation')}</Text>
                  </Pressable>
                ) : (
                  <View />
                )}
                <Text style={styles.msgTime}>{timeLabel(m.created_at)}</Text>
              </View>
            </View>
          );
        })}
      </ScrollView>

      <Pressable onLongPress={unlink} delayLongPress={1200} style={styles.unlink} accessibilityRole="button">
        <Text style={styles.unlinkText}>{t('unlinkPhone')}</Text>
      </Pressable>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  screen: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 6 },
  brand: { fontSize: 18, fontWeight: '900', color: colors.sea },
  fisher: { fontSize: 30, fontWeight: '900', color: colors.ink, marginTop: 4 },
  sub: { fontSize: 15, color: colors.inkSoft },
  status: { marginHorizontal: 16, borderRadius: 16, padding: 14 },
  statusText: { fontSize: 20, fontWeight: '900', color: colors.white },
  statusSub: { fontSize: 14, fontWeight: '600', color: colors.white, opacity: 0.9, marginTop: 2 },
  sos: { marginHorizontal: 16, marginTop: 10, borderRadius: 16, padding: 14, backgroundColor: colors.unsafe, gap: 6 },
  sosTitle: { fontSize: 22, fontWeight: '900', color: colors.white },
  sosTime: { fontSize: 14, fontWeight: '700', color: colors.white },
  sosButtons: { flexDirection: 'row', gap: 8, marginTop: 4 },
  threadTitle: { fontSize: 14, fontWeight: '800', color: colors.inkSoft, textTransform: 'uppercase', letterSpacing: 0.6, marginHorizontal: 16, marginTop: 14, marginBottom: 6 },
  offline: { fontSize: 13, fontWeight: '700', color: colors.unsafe, marginHorizontal: 16 },
  thread: { paddingHorizontal: 16, paddingBottom: 16, gap: 10 },
  empty: { fontSize: 16, lineHeight: 23, color: colors.inkSoft, textAlign: 'center', marginTop: 24 },
  bubble: { alignSelf: 'flex-start', maxWidth: '92%', backgroundColor: colors.card, borderRadius: 16, borderTopLeftRadius: 4, padding: 12, borderWidth: 1, borderColor: colors.line, gap: 4 },
  bubbleUrgent: { borderColor: colors.unsafe, borderWidth: 2, backgroundColor: '#FFF1F2' },
  sender: { fontSize: 12, fontWeight: '800', color: colors.inkSoft },
  msgText: { fontSize: 17, lineHeight: 24, color: colors.ink },
  msgFoot: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 2 },
  msgLink: { fontSize: 14, fontWeight: '800', color: colors.sea },
  msgTime: { fontSize: 12, color: colors.inkSoft },
  unlink: { minHeight: TOUCH, alignItems: 'center', justifyContent: 'center' },
  unlinkText: { fontSize: 12, color: colors.inkSoft },
});
