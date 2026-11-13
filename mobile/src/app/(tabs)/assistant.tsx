import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, Vibration, View , type ScrollViewInstance } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Icon } from '../../components/art';
import { LevelPill } from '../../components/forecast';
import { Banner, BigButton } from '../../components/ui';
import { ApiError, api } from '../../lib/api';
import { notifyAt } from '../../lib/notifications';
import { speak, startListening, stopSpeaking, voiceInputAvailable } from '../../lib/speech';
import { useApp } from '../../lib/store';
import { TOUCH, colors } from '../../lib/theme';
import type { AssistantTurn, ScheduledTrip } from '../../lib/types';

// English only for now; Malayalam voice comes later.
const VOICE_LANG = 'en' as const;
const HOUR = 60 * 60 * 1000;
const PERSONA = 'Meera';
// The voice assistant is English-only, so these stay out of i18n for now.
const GREETING = `Hi, I'm ${PERSONA}. Ask me how the sea looks, hour by hour, or tell me about your trip.`;
const SUGGESTIONS = [
  'When should I go tomorrow?',
  'Is 4 AM ok tomorrow?',
  'How are the waves tomorrow morning?',
  'Plan a trip tomorrow, 5 AM to 11 AM',
  'What trips do I have?',
  'I need another hour',
  'What are fishers saying at the harbour?',
];

/** Phone-side reminder an hour before a confirmed trip, so it rings even with no signal. */
function remindLocally(s: ScheduledTrip, t: ReturnType<typeof useApp>['t']): void {
  const when = new Date(new Date(s.depart_at).getTime() - HOUR);
  void notifyAt(when, t('tripReminderTitle'), t('tripReminderBody', { time: s.depart_label }));
}

export default function AssistantScreen() {
  const { profile, t, ensureRegistered } = useApp();
  const token = profile?.token;
  const router = useRouter();

  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [scheduled, setScheduled] = useState<ScheduledTrip[]>([]);
  const [proposal, setProposal] = useState<ScheduledTrip | null>(null);
  const [text, setText] = useState('');
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sosHint, setSosHint] = useState(false);
  const [voiceOut, setVoiceOut] = useState(true);
  const [speaking, setSpeaking] = useState(false);

  const talk = useCallback((line: string) => {
    speak(line, VOICE_LANG, { onStart: () => setSpeaking(true), onDone: () => setSpeaking(false) });
  }, []);
  const hush = useCallback(() => {
    stopSpeaking();
    setSpeaking(false);
  }, []);

  const scrollRef = useRef<ScrollViewInstance>(null);
  const stopRef = useRef<(() => void) | null>(null);
  const heardRef = useRef('');
  const releasedRef = useRef(false);
  const [canUseVoice] = useState(voiceInputAvailable);

  const load = useCallback(async () => {
    if (!profile?.token) return;
    try {
      const [history, upcoming] = await Promise.all([api.assistantHistory(), api.scheduled()]);
      setTurns(history);
      setScheduled(upcoming);
      setProposal(upcoming.find((s) => s.status === 'proposed') ?? null);
    } catch {
      // offline: keep what is on screen
    }
  }, [profile?.token]);

  useFocusEffect(
    useCallback(() => {
      void load();
      return () => hush();
    }, [load, hush]),
  );

  useEffect(() => {
    const id = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 50);
    return () => clearTimeout(id);
  }, [turns, proposal]);

  const send = useCallback(
    async (raw: string) => {
      const message = raw.trim();
      if (!message || busy) return;
      hush();
      setBusy(true);
      setError(null);
      setText('');
      setTurns((prev) => [...prev, { id: `u${Date.now()}`, role: 'user', text: message }]);
      try {
        if (!token && !(await ensureRegistered())) throw new ApiError(t('noConnection'), 0, true);
        const out = await api.assistantChat(message);
        setTurns((prev) => [...prev, { id: `a${Date.now()}`, role: 'assistant', text: out.reply }]);
        setScheduled(out.scheduled);
        setProposal(out.proposal?.status === 'proposed' ? out.proposal : null);
        if (out.action === 'confirm_schedule' && out.proposal?.status === 'scheduled') remindLocally(out.proposal, t);
        setSosHint(out.action === 'sos_help');
        if (out.action === 'sos_help') Vibration.vibrate([0, 400, 150, 400]);
        if (voiceOut) talk(out.reply);
      } catch (err) {
        const e = err instanceof ApiError ? err : null;
        const msg = e?.status === 429 ? t('slowDown', { n: e.retryAfter || 30 }) : e?.message || t('noConnection');
        setError(msg);
        if (voiceOut) talk(msg);
      } finally {
        setBusy(false);
      }
    },
    [busy, ensureRegistered, hush, token, t, talk, voiceOut],
  );

  const micDown = async () => {
    if (listening || busy) return;
    hush();
    setError(null);
    heardRef.current = '';
    releasedRef.current = false;
    setListening(true);
    const stop = await startListening(VOICE_LANG, {
      onText: (heard) => {
        heardRef.current = heard;
        setText(heard);
      },
      onEnd: () => {
        stopRef.current = null;
        setListening(false);
        if (heardRef.current.trim()) void send(heardRef.current);
      },
      onError: (code) => {
        if (code === 'not-allowed') setError(t('micDenied'));
        else if (code === 'network') setError(t('voiceNeedsNetwork'));
        else if (code === 'no-speech') setError(t('didNotHear'));
      },
    });
    if (!stop) {
      setListening(false);
      setError((cur) => cur ?? t('voiceUnavailable'));
      return;
    }
    stopRef.current = stop;
    if (releasedRef.current) stop();
  };

  const micUp = () => {
    releasedRef.current = true;
    stopRef.current?.();
  };

  const decide = async (yes: boolean) => {
    if (!proposal) return;
    setBusy(true);
    try {
      if (yes) remindLocally(await api.confirmScheduled(proposal.id), t);
      else await api.cancelScheduled(proposal.id);
      setProposal(null);
      setScheduled(await api.scheduled());
    } catch {
      setError(t('noConnection'));
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    hush();
    setTurns([]);
    try {
      await api.clearAssistantHistory();
    } catch {
      // cleared on screen anyway
    }
  };

  if (!profile) return null;

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <View style={styles.persona}>
          <View style={[styles.avatar, speaking && styles.avatarOn]}>
            <Text style={styles.avatarText}>{PERSONA[0]}</Text>
          </View>
          <View>
            <Text style={styles.title}>{PERSONA}</Text>
            <Text style={styles.subtitle}>{speaking ? 'Speaking… tap to stop' : t('assistantTitle')}</Text>
          </View>
        </View>
        {speaking ? (
          <Pressable onPress={hush} accessibilityRole="button" accessibilityLabel="Stop speaking" style={[styles.clear, styles.iconRow]}>
            <Icon name="speaker" size={20} color={colors.inkSoft} />
            <Text style={styles.clearText}>Stop</Text>
          </Pressable>
        ) : (
          <Pressable onPress={clear} accessibilityRole="button" style={styles.clear}>
            <Text style={styles.clearText}>{t('clearChat')}</Text>
          </Pressable>
        )}
      </View>

      <ScrollView ref={scrollRef} contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        {turns.length === 0 ? (
          <View style={styles.welcome}>
            <View style={[styles.bubble, styles.theirs]}>
              <Text style={styles.bubbleText}>{GREETING}</Text>
            </View>
            <View style={styles.chips}>
              {SUGGESTIONS.map((s) => (
                <Pressable key={s} onPress={() => send(s)} disabled={busy} style={styles.chip} accessibilityRole="button">
                  <Text style={styles.chipText}>{s}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        ) : null}
        {turns.map((turn) => (
          <Pressable
            key={turn.id}
            onLongPress={turn.role === 'assistant' ? () => talk(turn.text) : undefined}
            style={[styles.bubble, turn.role === 'user' ? styles.mine : styles.theirs]}
          >
            {turn.role === 'assistant' ? <Text style={styles.who}>{PERSONA}</Text> : null}
            <Text style={[styles.bubbleText, turn.role === 'user' && styles.mineText]}>{turn.text}</Text>
          </Pressable>
        ))}
        {busy ? <ActivityIndicator color={colors.sea} style={styles.spinner} /> : null}

        {sosHint ? <Banner tone="danger" icon="🆘" text={t('pressSosNow')} /> : null}

        {proposal ? (
          <View style={styles.proposal}>
            <View style={styles.rowBetween}>
              <Text style={styles.proposalTitle}>{t('proposalTitle')}</Text>
              <LevelPill level={proposal.verdict} />
            </View>
            <Text style={styles.proposalWhen}>
              {proposal.day_label}: {proposal.depart_label} → {proposal.return_label}
            </Text>
            {proposal.note ? <Text style={styles.small}>{proposal.note}</Text> : null}
            <View style={styles.row}>
              <BigButton label={t('confirm')} icon="✔" onPress={() => decide(true)} color={colors.safe} style={styles.flex} busy={busy} />
              <BigButton label={t('cancel')} onPress={() => decide(false)} color={colors.line} textColor={colors.ink} style={styles.flex} />
            </View>
          </View>
        ) : null}

        {scheduled.filter((s) => s.status === 'scheduled').length > 0 ? (
          <View style={styles.scheduledBox}>
            <Text style={styles.sectionTitle}>{t('scheduledTrips')}</Text>
            {scheduled
              .filter((s) => s.status === 'scheduled')
              .map((s) => (
                <Pressable key={s.id} onPress={() => router.push('/trip')} style={styles.scheduledRow} accessibilityRole="button">
                  <View style={[styles.iconRow, styles.flex]}>
                    <Icon name="sail" size={20} color={colors.sea} />
                    <Text style={styles.scheduledText}>
                      {s.day_label} · {s.depart_label} → {s.return_label}
                    </Text>
                  </View>
                  <LevelPill level={s.verdict} />
                </Pressable>
              ))}
          </View>
        ) : null}
      </ScrollView>

      <View style={styles.footer}>
        {error ? (
          <View style={[styles.iconRow, styles.center]}>
            <Icon name="alert" size={18} color={colors.unsafe} />
            <Text style={styles.error}>{error}</Text>
          </View>
        ) : null}
        <View style={styles.inputRow}>
          <TextInput
            value={text}
            onChangeText={setText}
            placeholder={t('typeMessage')}
            placeholderTextColor={colors.inkSoft}
            style={styles.input}
            returnKeyType="send"
            onSubmitEditing={() => send(text)}
            editable={!listening}
          />
          <Pressable
            onPress={() => send(text)}
            disabled={busy || !text.trim()}
            style={[styles.sendBtn, (busy || !text.trim()) && styles.off]}
            accessibilityRole="button"
            accessibilityLabel={t('ask')}
          >
            <Icon name="send" size={24} color={colors.white} />
          </Pressable>
        </View>
        <View style={styles.micRow}>
          <View style={styles.voiceToggle}>
            <Switch value={voiceOut} onValueChange={setVoiceOut} />
            <Text style={styles.small}>{t('speakReplies')}</Text>
          </View>
          <Pressable
            onPressIn={micDown}
            onPressOut={micUp}
            disabled={busy || !canUseVoice}
            accessibilityRole="button"
            accessibilityLabel={t('holdToTalk')}
            style={[styles.mic, listening && styles.micOn, (busy || !canUseVoice) && styles.off]}
          >
            <Icon name="mic" size={38} color={colors.white} />
          </Pressable>
          <Text style={[styles.small, styles.micLabel]}>
            {busy ? t('assistantThinking') : listening ? t('listening') : canUseVoice ? t('holdToTalk') : t('voiceUnavailable')}
          </Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  screen: { flex: 1, backgroundColor: colors.bg },
  // Right padding leaves room for the floating Tools button the tab layout draws top-right.
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingLeft: 16, paddingRight: 92, paddingVertical: 8 },
  title: { fontSize: 22, fontWeight: '900', color: colors.sea },
  subtitle: { fontSize: 13, color: colors.inkSoft },
  iconRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  center: { justifyContent: 'center' },
  persona: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  avatar: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.sea, alignItems: 'center', justifyContent: 'center',
    borderWidth: 3, borderColor: colors.card,
  },
  avatarOn: { borderColor: colors.safe },
  avatarText: { fontSize: 20, fontWeight: '900', color: colors.white },
  welcome: { gap: 12, marginTop: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    minHeight: TOUCH, justifyContent: 'center', paddingHorizontal: 14, borderRadius: 22,
    borderWidth: 2, borderColor: colors.sea, backgroundColor: colors.card,
  },
  chipText: { fontSize: 15, fontWeight: '700', color: colors.sea },
  who: { fontSize: 12, fontWeight: '800', color: colors.sea, marginBottom: 2 },
  clear: { minHeight: TOUCH, justifyContent: 'center', paddingHorizontal: 8 },
  clearText: { fontSize: 15, fontWeight: '700', color: colors.inkSoft },
  body: { paddingHorizontal: 16, paddingBottom: 16, gap: 10 },
  hint: { fontSize: 17, lineHeight: 25, color: colors.inkSoft, textAlign: 'center', marginTop: 24 },
  bubble: { maxWidth: '86%', borderRadius: 16, paddingHorizontal: 14, paddingVertical: 10 },
  mine: { alignSelf: 'flex-end', backgroundColor: colors.sea },
  theirs: { alignSelf: 'flex-start', backgroundColor: colors.card, borderWidth: 1, borderColor: colors.line },
  bubbleText: { fontSize: 18, lineHeight: 26, color: colors.ink },
  mineText: { color: colors.white },
  spinner: { alignSelf: 'flex-start', marginLeft: 12 },
  proposal: { borderRadius: 16, borderWidth: 3, borderColor: colors.sea, backgroundColor: colors.card, padding: 14, gap: 8 },
  proposalTitle: { fontSize: 17, fontWeight: '800', color: colors.ink, flexShrink: 1 },
  proposalWhen: { fontSize: 20, fontWeight: '900', color: colors.ink },
  row: { flexDirection: 'row', gap: 8 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  scheduledBox: { gap: 6, marginTop: 6 },
  sectionTitle: { fontSize: 16, fontWeight: '800', color: colors.inkSoft },
  scheduledRow: {
    minHeight: TOUCH, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: colors.card, borderRadius: 12, borderWidth: 1, borderColor: colors.line, paddingHorizontal: 12,
  },
  scheduledText: { fontSize: 16, fontWeight: '700', color: colors.ink, flexShrink: 1 },
  footer: { borderTopWidth: 1, borderColor: colors.line, backgroundColor: colors.card, padding: 12, paddingBottom: 96, gap: 8 },
  error: { fontSize: 15, fontWeight: '700', color: colors.unsafe, textAlign: 'center' },
  inputRow: { flexDirection: 'row', gap: 8 },
  input: {
    flex: 1, minHeight: TOUCH, borderWidth: 2, borderColor: colors.line, borderRadius: 12,
    paddingHorizontal: 14, fontSize: 17, color: colors.ink, backgroundColor: colors.white,
  },
  sendBtn: { width: TOUCH + 4, minHeight: TOUCH, borderRadius: 12, backgroundColor: colors.sea, alignItems: 'center', justifyContent: 'center' },
  sendText: { fontSize: 24, color: colors.white, fontWeight: '900' },
  off: { opacity: 0.4 },
  micRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  voiceToggle: { flexDirection: 'row', alignItems: 'center', gap: 4, width: 110 },
  mic: {
    width: 84, height: 84, borderRadius: 42, backgroundColor: colors.sea, alignItems: 'center', justifyContent: 'center',
    borderWidth: 5, borderColor: '#9DB4CC',
  },
  micOn: { backgroundColor: colors.unsafe, borderColor: '#F5B5BA', transform: [{ scale: 1.08 }] },
  micIcon: { fontSize: 38 },
  micLabel: { width: 110 },
  small: { fontSize: 13, color: colors.inkSoft, textAlign: 'center' },
});
