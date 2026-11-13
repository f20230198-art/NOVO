import { useRouter } from 'expo-router';
import React, { useCallback, useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ContactsEditor, HarbourPicker, type Harbour } from '../components/pickers';
import { BigButton, BoatPicker, Field } from '../components/ui';
import { LANGUAGES, translate, type Translate } from '../i18n';
import { ApiError, api } from '../lib/api';
import { getPosition } from '../lib/location';
import { registerForPush } from '../lib/notifications';
import { useApp } from '../lib/store';
import { HARBOURS, colors } from '../lib/theme';
import type { BoatType, Contact, Lang } from '../lib/types';

const STEPS = 5;

/** First screen: is this phone a fisher's, or a family member's? */
function WhoUsesThisPhone({ onFisher }: { onFisher: () => void }) {
  const { apiUrl, setApiUrl, setFamily } = useApp();
  const router = useRouter();
  const t = useCallback<Translate>((key, params) => translate('en', key, params), []);
  const [family, setFamilyMode] = useState(false);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showServer, setShowServer] = useState(false);
  const [url, setUrl] = useState(apiUrl);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      if (url.trim() && url.trim() !== apiUrl) await setApiUrl(url);
      const push = await registerForPush();
      const link = await api.familyLink(code.trim(), push);
      await setFamily(link);
      router.replace('/family');
    } catch (err) {
      setError(err instanceof ApiError && !err.offline ? err.message : t('noConnection'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.screen}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.header}>
          <Text style={styles.brand}>🌊 {t('appName')}</Text>
          <Text style={styles.title}>{family ? t('enterCode') : t('whoUses')}</Text>
        </View>
        <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
          {!family ? (
            <>
              <Pressable onPress={onFisher} style={styles.roleCard} accessibilityRole="button">
                <Text style={styles.roleIcon}>⛵</Text>
                <View style={styles.flex}>
                  <Text style={styles.roleTitle}>{t('iFish')}</Text>
                  <Text style={styles.roleHint}>{t('iFishHint')}</Text>
                </View>
              </Pressable>
              <Pressable onPress={() => setFamilyMode(true)} style={styles.roleCard} accessibilityRole="button">
                <Text style={styles.roleIcon}>👨‍👩‍👧</Text>
                <View style={styles.flex}>
                  <Text style={styles.roleTitle}>{t('iAmFamily')}</Text>
                  <Text style={styles.roleHint}>{t('iAmFamilyHint')}</Text>
                </View>
              </Pressable>
            </>
          ) : (
            <View>
              <Text style={styles.roleHint}>{t('enterCodeHint')}</Text>
              <TextInput
                value={code}
                onChangeText={(v) => setCode(v.replace(/[^0-9]/g, '').slice(0, 6))}
                keyboardType="number-pad"
                maxLength={6}
                placeholder="000000"
                placeholderTextColor={colors.line}
                style={styles.codeInput}
                accessibilityLabel={t('enterCode')}
                autoFocus
              />
              {error ? <Text style={styles.error}>⚠ {error}</Text> : null}
              <BigButton label={busy ? t('linking') : t('linkPhone')} icon="🔗" onPress={connect} busy={busy} disabled={code.length !== 6} />
              <BigButton label={t('back')} onPress={() => setFamilyMode(false)} color={colors.line} textColor={colors.ink} style={styles.spaced} />
            </View>
          )}

          <Pressable onPress={() => setShowServer((v) => !v)} accessibilityRole="button">
            <Text style={styles.link}>{showServer ? '▲' : '▼'} {t('serverSettings')}</Text>
          </Pressable>
          {showServer ? (
            <View>
              <Field label={t('serverUrl')} value={url} onChangeText={setUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" />
              <BigButton label={t('save')} icon="💾" onPress={() => setApiUrl(url)} color={colors.inkSoft} />
            </View>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

export default function Onboarding() {
  const [role, setRole] = useState<'ask' | 'fisher'>('ask');
  if (role === 'ask') return <WhoUsesThisPhone onFisher={() => setRole('fisher')} />;
  return <FisherOnboarding />;
}

function FisherOnboarding() {
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
  roleCard: {
    minHeight: 110, borderRadius: 18, borderWidth: 2, borderColor: colors.line, backgroundColor: colors.white,
    padding: 18, flexDirection: 'row', alignItems: 'center', gap: 16,
  },
  roleIcon: { fontSize: 44 },
  roleTitle: { fontSize: 22, fontWeight: '900', color: colors.ink },
  roleHint: { fontSize: 15, color: colors.inkSoft, lineHeight: 21 },
  codeInput: {
    fontSize: 44, fontWeight: '900', letterSpacing: 10, textAlign: 'center', color: colors.ink,
    borderWidth: 2, borderColor: colors.sea, borderRadius: 16, backgroundColor: colors.white, paddingVertical: 14, marginVertical: 18,
  },
  spaced: { marginTop: 10 },
  link: { fontSize: 14, fontWeight: '700', color: colors.inkSoft, marginTop: 12, textAlign: 'center' },
});
