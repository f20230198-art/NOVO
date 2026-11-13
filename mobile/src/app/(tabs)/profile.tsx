import { useFocusEffect } from 'expo-router';
import React, { useCallback, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { ContactsEditor, HarbourPicker, type Harbour } from '../../components/pickers';
import { Banner, BigButton, BoatPicker, Card, Choice, Field, Screen, SectionTitle } from '../../components/ui';
import { LANGUAGES } from '../../i18n';
import { api } from '../../lib/api';
import { useApp } from '../../lib/store';
import { colors } from '../../lib/theme';
import type { Contact } from '../../lib/types';

export default function ProfileScreen() {
  const { profile, contacts, t, updateProfile, addContact, removeContact, setSimOpen } = useApp();

  const [name, setName] = useState(profile?.name ?? '');
  const [phone, setPhone] = useState(profile?.phone ?? '');
  const [harbour, setHarbour] = useState<Harbour>({
    lat: profile?.home_lat ?? 0,
    lon: profile?.home_lon ?? 0,
    name: profile?.home_name ?? '',
  });
  const [savedNote, setSavedNote] = useState(false);
  const [codes, setCodes] = useState<Contact[]>([]);

  // Family codes come from the server (each contact gets one when it is saved there).
  useFocusEffect(
    useCallback(() => {
      if (!profile?.token) return;
      let cancelled = false;
      api.listContacts().then((list) => !cancelled && setCodes(list)).catch(() => {});
      const id = setInterval(() => api.listContacts().then((list) => !cancelled && setCodes(list)).catch(() => {}), 8000);
      return () => {
        cancelled = true;
        clearInterval(id);
      };
    // contacts.length: fetch the family codes again after a contact is added or removed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [profile?.token, contacts.length]),
  );

  if (!profile) return null;

  const saveDetails = async () => {
    await updateProfile({
      name: name.trim() || profile.name,
      phone: phone.trim(),
      home_lat: harbour.lat,
      home_lon: harbour.lon,
      home_name: harbour.name.trim() || profile.home_name,
    });
    setSavedNote(true);
    setTimeout(() => setSavedNote(false), 2500);
  };

  return (
    // Long-press the title to open the simulation pop-up.
    <Screen title={t('profile')} onTitleLongPress={() => setSimOpen(true)}>
      {!profile.token ? <Banner icon="📴" tone="warn" text={t('notRegistered')} /> : null}

      <Card>
        <SectionTitle>{t('yourBoat')}</SectionTitle>
        {/* Applies at once: the home screen verdict changes with the boat. */}
        <BoatPicker value={profile.boat_type} onChange={(boat_type) => updateProfile({ boat_type })} />
      </Card>

      <Card>
        <SectionTitle>{t('language')}</SectionTitle>
        <View style={styles.row}>
          {LANGUAGES.map((l) => (
            <Choice key={l.code} label={l.label} selected={profile.language === l.code} onPress={() => updateProfile({ language: l.code })} />
          ))}
        </View>
      </Card>

      <Card>
        <SectionTitle>{t('aboutYou')}</SectionTitle>
        <Field label={t('yourName')} value={name} onChangeText={setName} />
        <Field label={t('yourPhone')} value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
        <SectionTitle>{t('homeHarbour')}</SectionTitle>
        <HarbourPicker value={harbour} onChange={setHarbour} t={t} />
        <BigButton label={savedNote ? t('saved') : t('save')} icon={savedNote ? '✔' : '💾'} onPress={saveDetails} color={savedNote ? colors.safe : colors.sea} />
      </Card>

      <Card>
        <SectionTitle>{t('emergencyContacts')}</SectionTitle>
        <ContactsEditor contacts={contacts} onAdd={addContact} onRemove={removeContact} t={t} />
      </Card>

      {codes.length > 0 ? (
        <Card>
          <SectionTitle>📲 {t('familyCodes')}</SectionTitle>
          <Text style={styles.hint}>{t('familyCodesHint')}</Text>
          {codes.map((c) => (
            <View key={c.id} style={styles.codeRow}>
              <View style={styles.flex}>
                <Text style={styles.codeName}>
                  {c.name}
                  {c.relation ? ` (${c.relation})` : ''}
                </Text>
                <Text style={[styles.codeState, c.family_app && styles.codeLinked]}>
                  {c.family_app ? `✔ ${t('familyLinked')}` : t('familyNotLinked')}
                </Text>
              </View>
              <Text style={styles.code} selectable accessibilityLabel={`${c.name} ${c.link_code ?? ''}`}>
                {c.link_code ? `${c.link_code.slice(0, 3)} ${c.link_code.slice(3)}` : '—'}
              </Text>
            </View>
          ))}
        </Card>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  hint: { fontSize: 14, lineHeight: 20, color: colors.inkSoft, marginBottom: 8 },
  codeRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderTopWidth: 1, borderColor: colors.line },
  codeName: { fontSize: 17, fontWeight: '800', color: colors.ink },
  codeState: { fontSize: 13, color: colors.inkSoft },
  codeLinked: { color: colors.safe, fontWeight: '800' },
  code: { fontSize: 26, fontWeight: '900', color: colors.sea, letterSpacing: 2, fontVariant: ['tabular-nums'] },
});
