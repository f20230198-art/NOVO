import React, { useCallback, useEffect, useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError, api } from '../lib/api';
import { useApp } from '../lib/store';
import { TOUCH, colors } from '../lib/theme';
import type { Buddy } from '../lib/types';
import { Icon } from './art';

const STATUS_COLOR: Record<Buddy['status'], string> = {
  ashore: colors.inkSoft,
  active: colors.sea,
  overdue: colors.unsafe,
  emergency: colors.unsafe,
};

/**
 * Buddy boats: fishers who are told at once when this fisher is overdue or sends SOS.
 * A buddy's position appears only while that buddy may need help.
 */
export function BuddyBoats() {
  const { t } = useApp();
  const [buddies, setBuddies] = useState<Buddy[]>([]);
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setBuddies(await api.buddies());
    } catch {
      // offline: keep what is on screen
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  const add = async () => {
    if (!phone.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.addBuddy(phone.trim());
      setPhone('');
      await load();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 404 ? t('buddyNotFound') : t('noConnection'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    try {
      await api.removeBuddy(id);
      await load();
    } catch {
      setError(t('noConnection'));
    }
  };

  return (
    <View style={styles.wrap}>
      <View style={styles.titleRow}>
        <Icon name="people" size={24} color={colors.ink} />
        <Text style={styles.title}>{t('buddyTitle')}</Text>
      </View>
      <Text style={styles.hint}>{t('buddyHint')}</Text>

      {buddies.length === 0 ? <Text style={styles.hint}>{t('buddyNone')}</Text> : null}
      {buddies.map((b) => {
        const alarm = b.status === 'overdue' || b.status === 'emergency';
        return (
          <View key={b.id} style={[styles.row, alarm && styles.rowAlarm]}>
            <View style={styles.flex}>
              <Text style={styles.name}>{b.name}</Text>
              <Text style={[styles.status, { color: alarm ? colors.unsafe : STATUS_COLOR[b.status] }]}>
                {t(`buddy_${b.status}`)}
                {b.distance_km != null ? ` · ${t('buddyAway', { km: b.distance_km })}` : ''}
              </Text>
              {alarm && b.lat != null && b.lon != null ? (
                <Pressable
                  onPress={() => void Linking.openURL(`https://maps.google.com/?q=${b.lat},${b.lon}`)}
                  accessibilityRole="link"
                  style={styles.mapLink}
                >
                  <Icon name="pin" size={20} color={colors.white} />
                  <Text style={styles.mapLinkText}>{t('buddyOpenMap')}</Text>
                </Pressable>
              ) : null}
            </View>
            <Pressable onPress={() => remove(b.id)} accessibilityRole="button" accessibilityLabel={`${t('buddyRemove')} ${b.name}`} style={styles.remove}>
              <Icon name="cross" size={20} color={colors.inkSoft} />
            </Pressable>
          </View>
        );
      })}

      <View style={styles.addRow}>
        <TextInput
          value={phone}
          onChangeText={setPhone}
          placeholder={t('buddyPhone')}
          placeholderTextColor={colors.inkSoft}
          accessibilityLabel={t('buddyPhone')}
          keyboardType="phone-pad"
          style={styles.input}
          onSubmitEditing={add}
        />
        <Pressable
          onPress={add}
          disabled={busy || !phone.trim()}
          accessibilityRole="button"
          accessibilityLabel={t('buddyAdd')}
          style={[styles.addButton, (busy || !phone.trim()) && styles.addOff]}
        >
          <Icon name="plus" size={26} color={colors.white} weight={3} />
        </Pressable>
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  wrap: { gap: 10 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 20, fontWeight: '800', color: colors.ink },
  hint: { fontSize: 15, lineHeight: 21, color: colors.inkSoft },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderTopWidth: 1, borderTopColor: colors.line },
  rowAlarm: { backgroundColor: '#FBE4E1', marginHorizontal: -16, paddingHorizontal: 16 },
  name: { fontSize: 19, fontWeight: '800', color: colors.ink },
  status: { fontSize: 16, fontWeight: '700', marginTop: 2 },
  mapLink: {
    flexDirection: 'row', alignItems: 'center', gap: 8, alignSelf: 'flex-start', minHeight: TOUCH - 8,
    backgroundColor: colors.unsafe, borderRadius: 4, paddingHorizontal: 14, marginTop: 8,
  },
  mapLinkText: { fontSize: 16, fontWeight: '800', color: colors.white },
  remove: { width: TOUCH, height: TOUCH, alignItems: 'center', justifyContent: 'center' },
  addRow: { flexDirection: 'row', gap: 8 },
  input: {
    flex: 1, minHeight: TOUCH, borderWidth: 2, borderColor: colors.ink, borderRadius: 4, paddingHorizontal: 14,
    fontSize: 18, color: colors.ink, backgroundColor: colors.white,
  },
  addButton: { width: TOUCH + 4, minHeight: TOUCH, borderRadius: 4, backgroundColor: colors.sea, alignItems: 'center', justifyContent: 'center' },
  addOff: { opacity: 0.4 },
  error: { fontSize: 15, fontWeight: '700', color: colors.unsafe },
});
