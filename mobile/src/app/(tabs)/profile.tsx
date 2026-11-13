import React, { useEffect, useState } from 'react';
import { Modal, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ContactsEditor, HarbourPicker, type Harbour } from '../../components/pickers';
import { Banner, BigButton, BoatPicker, Card, Choice, Field, Screen, SectionTitle } from '../../components/ui';
import { LANGUAGES } from '../../i18n';
import { api } from '../../lib/api';
import { useApp } from '../../lib/store';
import { colors } from '../../lib/theme';

const SCENARIOS = ['real', 'calm', 'rough', 'storm', 'worsening'] as const;

export default function ProfileScreen() {
  const { profile, contacts, trip, apiUrl, t, updateProfile, addContact, removeContact, setApiUrl, ensureRegistered } = useApp();

  const [name, setName] = useState(profile?.name ?? '');
  const [phone, setPhone] = useState(profile?.phone ?? '');
  const [harbour, setHarbour] = useState<Harbour>({
    lat: profile?.home_lat ?? 0,
    lon: profile?.home_lon ?? 0,
    name: profile?.home_name ?? '',
  });
  const [savedNote, setSavedNote] = useState(false);

  const [demo, setDemo] = useState(false);
  const [url, setUrl] = useState(apiUrl);
  const [scenario, setScenario] = useState<string | null>(null);
  const [demoNote, setDemoNote] = useState<string | null>(null);
  const [demoBusy, setDemoBusy] = useState(false);

  useEffect(() => setUrl(apiUrl), [apiUrl]);

  useEffect(() => {
    if (!demo) return;
    api
      .health()
      .then((h) => setScenario(h.scenario))
      .catch(() => setDemoNote(t('noConnection')));
  }, [demo, apiUrl, t]);

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

  const run = async (action: () => Promise<string>) => {
    setDemoBusy(true);
    setDemoNote(null);
    try {
      setDemoNote(await action());
    } catch {
      setDemoNote(t('noConnection'));
    } finally {
      setDemoBusy(false);
    }
  };

  return (
    <Screen title={t('profile')} onTitleLongPress={() => setDemo(true)}>
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

      {/* Hidden demo panel: long-press the "Profile" title. */}
      <Modal visible={demo} animationType="slide" onRequestClose={() => setDemo(false)}>
        <ScrollView contentContainerStyle={styles.demoBody} keyboardShouldPersistTaps="handled">
          <Text style={styles.demoTitle}>🎬 {t('demoPanel')}</Text>
          {demoNote ? <Banner text={demoNote} /> : null}

          <Field label={t('serverUrl')} value={url} onChangeText={setUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" />
          <BigButton
            label={t('save')}
            icon="💾"
            onPress={() =>
              run(async () => {
                await setApiUrl(url);
                const health = await api.health();
                setScenario(health.scenario);
                await ensureRegistered();
                return `OK · ${url}`;
              })
            }
            busy={demoBusy}
          />

          <Text style={styles.demoSection}>{t('scenario')}</Text>
          <View style={styles.row}>
            {SCENARIOS.map((mode) => (
              <Choice
                key={mode}
                label={mode}
                selected={scenario === mode}
                onPress={() =>
                  run(async () => {
                    const result = await api.setScenario(mode);
                    setScenario(result.mode);
                    return `${t('scenario')}: ${result.mode}`;
                  })
                }
              />
            ))}
          </View>

          <BigButton label={t('seedData')} icon="🌱" onPress={() => run(async () => (await api.seed(), t('done')))} color={colors.inkSoft} busy={demoBusy} />
          <BigButton
            label={t('fastForward')}
            icon="⏩"
            color={colors.inkSoft}
            busy={demoBusy}
            onPress={() =>
              run(async () => {
                if (!trip) return t('noActiveTrip');
                await api.fastForward(trip.id);
                return t('done');
              })
            }
          />
          <BigButton
            label={t('loseSignal')}
            icon="📡"
            color={colors.inkSoft}
            busy={demoBusy}
            onPress={() =>
              run(async () => {
                if (!trip) return t('noActiveTrip');
                await api.loseSignal(trip.id);
                await api.tick();
                return t('done');
              })
            }
          />
          <BigButton
            label={t('runMonitor')}
            icon="🔁"
            color={colors.inkSoft}
            busy={demoBusy}
            onPress={() =>
              run(async () => {
                const r = await api.tick();
                return `checked ${r.checked} · overdue ${r.overdue} · alerts ${r.alerts}`;
              })
            }
          />
          <Text style={styles.demoHint}>
            user #{profile.user_id ?? '–'} · Telegram: /start {profile.token ?? '–'}
          </Text>
          <BigButton label={t('back')} onPress={() => setDemo(false)} color={colors.line} textColor={colors.ink} />
        </ScrollView>
      </Modal>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  demoBody: { padding: 16, paddingTop: 48, gap: 12, backgroundColor: colors.bg, flexGrow: 1 },
  demoTitle: { fontSize: 26, fontWeight: '900', color: colors.ink },
  demoSection: { fontSize: 18, fontWeight: '800', color: colors.ink, marginTop: 6 },
  demoHint: { fontSize: 13, color: colors.inkSoft },
});
