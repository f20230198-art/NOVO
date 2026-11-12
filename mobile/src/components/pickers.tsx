import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Translate } from '../i18n';
import { getPosition } from '../lib/location';
import { HARBOURS, TOUCH, colors } from '../lib/theme';
import type { Contact } from '../lib/types';
import { LeafletMap } from './LeafletMap';
import { BigButton, Choice, Field } from './ui';

export type Harbour = { lat: number; lon: number; name: string };

/** Map pin + GPS button + quick picks for the four test harbours. */
export function HarbourPicker({ value, onChange, t }: { value: Harbour; onChange: (h: Harbour) => void; t: Translate }) {
  const [locating, setLocating] = useState(false);
  const center = useMemo(() => ({ lat: value.lat, lon: value.lon }), [value.lat, value.lon]);

  const useGps = async () => {
    setLocating(true);
    const p = await getPosition(null, 8000);
    setLocating(false);
    if (p) onChange({ ...value, lat: p.lat, lon: p.lon });
  };

  return (
    <View style={styles.gap}>
      <Text style={styles.hint}>{t('harbourHint')}</Text>
      <LeafletMap center={center} zoom={12} pin={center} onPress={(lat, lon) => onChange({ ...value, lat, lon })} />
      <View style={styles.wrapRow}>
        {HARBOURS.map((h) => (
          <Choice
            key={h.name}
            label={h.name}
            selected={Math.abs(h.lat - value.lat) < 0.001 && Math.abs(h.lon - value.lon) < 0.001}
            onPress={() => onChange({ lat: h.lat, lon: h.lon, name: h.name })}
          />
        ))}
      </View>
      <BigButton label={t('useMyLocation')} icon="📍" onPress={useGps} busy={locating} color={colors.inkSoft} />
      <Field label={t('harbourName')} value={value.name} onChangeText={(name) => onChange({ ...value, name })} />
    </View>
  );
}

/** Contact list with remove buttons, the fixed Coast Guard row and an add form. */
export function ContactsEditor({
  contacts,
  onAdd,
  onRemove,
  t,
}: {
  contacts: Contact[];
  onAdd: (c: Contact) => void;
  onRemove: (index: number) => void;
  t: Translate;
}) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [relation, setRelation] = useState('');
  const canAdd = name.trim().length > 0 && phone.trim().length >= 4;

  const add = () => {
    if (!canAdd) return;
    onAdd({ name: name.trim(), phone: phone.trim(), relation: relation.trim() });
    setName('');
    setPhone('');
    setRelation('');
  };

  return (
    <View style={styles.gap}>
      <Text style={styles.hint}>{t('contactsHint')}</Text>
      {contacts.map((c, i) => (
        <View key={`${c.phone}-${i}`} style={styles.contactRow}>
          <Text style={styles.contactIcon}>👤</Text>
          <View style={styles.flex}>
            <Text style={styles.contactName}>{c.name}</Text>
            <Text style={styles.contactSub}>
              {c.phone}
              {c.relation ? ` · ${c.relation}` : ''}
            </Text>
          </View>
          <Pressable
            onPress={() => onRemove(i)}
            accessibilityRole="button"
            accessibilityLabel={`${t('remove')} ${c.name}`}
            style={styles.removeButton}
          >
            <Text style={styles.removeText}>✖</Text>
          </Pressable>
        </View>
      ))}
      <View style={[styles.contactRow, styles.coastGuard]}>
        <Text style={styles.contactIcon}>🚨</Text>
        <View style={styles.flex}>
          <Text style={styles.contactName}>{t('coastGuard')}</Text>
          <Text style={styles.contactSub}>{t('coastGuardHint')}</Text>
        </View>
      </View>
      <Field label={t('contactName')} value={name} onChangeText={setName} />
      <Field label={t('contactPhone')} value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
      <Field label={t('contactRelation')} value={relation} onChangeText={setRelation} />
      <BigButton label={t('addContact')} icon="➕" onPress={add} disabled={!canAdd} color={colors.inkSoft} />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  gap: { gap: 12 },
  hint: { fontSize: 15, color: colors.inkSoft, lineHeight: 21 },
  wrapRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  contactRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    minHeight: TOUCH + 8,
    backgroundColor: colors.white,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  coastGuard: { backgroundColor: '#FDECEE', borderColor: colors.unsafe },
  contactIcon: { fontSize: 26 },
  contactName: { fontSize: 17, fontWeight: '800', color: colors.ink },
  contactSub: { fontSize: 14, color: colors.inkSoft },
  removeButton: { width: TOUCH, height: TOUCH, alignItems: 'center', justifyContent: 'center' },
  removeText: { fontSize: 20, color: colors.unsafe, fontWeight: '900' },
});
