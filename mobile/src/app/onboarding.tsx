import { useRouter } from 'expo-router';
import React, { useCallback, useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ContactsEditor, HarbourPicker, type Harbour } from '../components/pickers';
import { BigButton, BoatPicker, Field } from '../components/ui';
import { LANGUAGES, translate, type Translate } from '../i18n';
import { getPosition } from '../lib/location';
import { useApp } from '../lib/store';
import { HARBOURS, colors } from '../lib/theme';
import type { BoatType, Contact, Lang } from '../lib/types';

const STEPS = 5;

export default function Onboarding() {
  const { completeOnboarding } = useApp();
  const router = useRouter();

  const [step, setStep] = useState(0);
  const [lang, setLang] = useState<Lang>('en');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [boat, setBoat] = useState<BoatType>('non_motorised');
  const [harbour, setHarbour] = useState<Harbour>({ ...HARBOURS[0] });
  const [harbourTouched, setHarbourTouched] = useState(false);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const t = useCallback<Translate>((key, params) => translate(lang, key, params), [lang]);

  // Prefill the harbour pin with GPS, unless the fisher already picked one.
  useEffect(() => {
    let cancelled = false;
    if (step === 3 && !harbourTouched) {
      getPosition(null, 6000).then((p) => {
        if (p && !cancelled) setHarbour((h) => ({ ...h, lat: p.lat, lon: p.lon, name: '' }));
      });
    }
    return () => {
      cancelled = true;
    };
  }, [step, harbourTouched]);

  const next = async () => {
    setError(null);
    if (step === 1 && !name.trim()) return setError(t('needName'));
    if (step < STEPS - 1) return setStep(step + 1);
    if (contacts.length === 0) return setError(t('needContact'));

    setSaving(true);
    await completeOnboarding(
      {
        name: name.trim(),
        phone: phone.trim(),
        language: lang,
        boat_type: boat,
        home_lat: harbour.lat,
        home_lon: harbour.lon,
        home_name: harbour.name.trim() || 'Home harbour',
      },
      contacts,
    );
    setSaving(false);
    router.replace('/');
  };

  const titles = [t('chooseLanguage'), t('aboutYou'), t('yourBoat'), t('homeHarbour'), t('emergencyContacts')];

  return (
    <SafeAreaView style={styles.screen}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.header}>
          <Text style={styles.brand}>🌊 {t('appName')}</Text>
          <View style={styles.dots}>
            {Array.from({ length: STEPS }, (_, i) => (
              <View key={i} style={[styles.dot, i <= step && styles.dotOn]} />
            ))}
          </View>
          <Text style={styles.title}>{titles[step]}</Text>
        </View>

        <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
          {step === 0 ? (
            <View style={styles.gap}>
              {LANGUAGES.map((l) => {
                const selected = l.code === lang;
                return (
                  <Pressable
                    key={l.code}
                    onPress={() => setLang(l.code)}
                    accessibilityRole="radio"
                    accessibilityState={{ selected }}
                    style={[styles.langCard, selected && styles.langCardOn]}
                  >
                    <Text style={[styles.langText, selected && styles.langTextOn]}>{l.label}</Text>
                    {selected ? <Text style={styles.langTextOn}>✔</Text> : null}
                  </Pressable>
                );
              })}
            </View>
          ) : null}

          {step === 1 ? (
            <View>
              <Field label={t('yourName')} value={name} onChangeText={setName} autoCapitalize="words" />
              <Field label={t('yourPhone')} value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
            </View>
          ) : null}

          {step === 2 ? <BoatPicker value={boat} onChange={setBoat} labels={t} /> : null}

          {step === 3 ? (
            <HarbourPicker
              value={harbour}
              t={t}
              onChange={(h) => {
                setHarbourTouched(true);
                setHarbour(h);
              }}
            />
          ) : null}

          {step === 4 ? (
            <ContactsEditor
              contacts={contacts}
              t={t}
              onAdd={(c) => setContacts((list) => [...list, c])}
              onRemove={(i) => setContacts((list) => list.filter((_, index) => index !== i))}
            />
          ) : null}

          {error ? <Text style={styles.error}>⚠ {error}</Text> : null}
          <Text style={styles.disclaimer}>{t('disclaimer')}</Text>
        </ScrollView>

        <View style={styles.footer}>
          {step > 0 ? (
            <BigButton label={t('back')} onPress={() => setStep(step - 1)} color={colors.line} textColor={colors.ink} style={styles.backButton} />
          ) : null}
          <BigButton
            label={step === STEPS - 1 ? t('finish') : t('next')}
            icon={step === STEPS - 1 ? '✔' : undefined}
            onPress={next}
            busy={saving}
            style={styles.flex}
          />
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  screen: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: 16, paddingTop: 8 },
  brand: { fontSize: 20, fontWeight: '900', color: colors.sea },
  dots: { flexDirection: 'row', gap: 6, marginTop: 10 },
  dot: { flex: 1, height: 6, borderRadius: 3, backgroundColor: colors.line },
  dotOn: { backgroundColor: colors.sea },
  title: { fontSize: 28, fontWeight: '900', color: colors.ink, marginTop: 14, marginBottom: 6 },
  body: { padding: 16, gap: 14, paddingBottom: 32 },
  gap: { gap: 12 },
  langCard: {
    minHeight: 84,
    borderRadius: 16,
    borderWidth: 2,
    borderColor: colors.line,
    backgroundColor: colors.white,
    paddingHorizontal: 20,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  langCardOn: { backgroundColor: colors.sea, borderColor: colors.sea },
  langText: { fontSize: 26, fontWeight: '800', color: colors.ink },
  langTextOn: { fontSize: 26, fontWeight: '800', color: colors.white },
  error: { fontSize: 16, fontWeight: '700', color: colors.unsafe },
  disclaimer: { fontSize: 13, lineHeight: 18, color: colors.inkSoft, textAlign: 'center' },
  footer: { flexDirection: 'row', gap: 10, padding: 16, borderTopWidth: 1, borderTopColor: colors.line, backgroundColor: colors.bg },
  backButton: { paddingHorizontal: 22 },
});
