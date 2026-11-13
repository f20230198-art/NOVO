import { useFocusEffect } from 'expo-router';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View , type ScrollViewInstance } from 'react-native';

import { Banner, BigButton, Card, Choice, Field, Screen, SectionTitle } from '../../components/ui';
import { ApiError, api } from '../../lib/api';
import { formatClock } from '../../lib/format';
import { useApp } from '../../lib/store';
import { TOUCH, colors } from '../../lib/theme';
import type { ChatMessage, CommunityEvent } from '../../lib/types';
import type { StringKey } from '../../i18n';

const KINDS = ['meeting', 'training', 'safety_drill', 'festival', 'cleanup', 'market', 'other'] as const;
const POLL_MS = 6000;
const HOUR = 60 * 60 * 1000;

function nextRoundHour(hoursAhead: number): Date {
  const d = new Date(Date.now() + hoursAhead * HOUR);
  d.setMinutes(0, 0, 0);
  return d;
}

function whenLabel(iso: string): string {
  const d = new Date(iso);
  return `${d.toDateString().slice(0, 10)} · ${formatClock(d)}`;
}

/** A chat channel: polls for new messages while it is on screen. */
function ChatPanel({ channel }: { channel: string }) {
  const { t } = useApp();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const lastId = useRef(0);
  const scrollRef = useRef<ScrollViewInstance>(null);

  const poll = useCallback(async () => {
    try {
      const fresh = await api.messages(channel, lastId.current);
      if (fresh.length) {
        lastId.current = fresh[fresh.length - 1].id;
        setMessages((prev) => [...prev, ...fresh.filter((m) => !prev.some((p) => p.id === m.id))]);
      }
      setError(null);
    } catch {
      setError(t('noConnection'));
    }
  }, [channel, t]);

  useEffect(() => {
    lastId.current = 0;
    // Switching channel clears the old thread before the new one loads.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMessages([]);
  }, [channel]);

  useFocusEffect(
    useCallback(() => {
      void poll();
      const id = setInterval(poll, POLL_MS);
      return () => clearInterval(id);
    }, [poll]),
  );

  useEffect(() => {
    const id = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 50);
    return () => clearTimeout(id);
  }, [messages.length]);

  const send = async () => {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    try {
      const msg = await api.postMessage(channel, body);
      setText('');
      lastId.current = Math.max(lastId.current, msg.id);
      setMessages((prev) => [...prev, msg]);
      setError(null);
    } catch (err) {
      const e = err instanceof ApiError ? err : null;
      setError(e?.status === 429 ? t('slowDown', { n: e.retryAfter || 30 }) : t('noConnection'));
    } finally {
      setSending(false);
    }
  };

  const flag = async (id: number) => {
    try {
      await api.flagMessage(id);
      setError(t('flagged'));
    } catch {
      // nothing else to do
    }
  };

  return (
    <View style={styles.chat}>
      <ScrollView ref={scrollRef} style={styles.chatScroll} contentContainerStyle={styles.chatBody} nestedScrollEnabled>
        {messages.length === 0 ? <Text style={styles.small}>{t('noMessages')}</Text> : null}
        {messages.map((m) => (
          <View key={m.id} style={[styles.msg, m.mine ? styles.msgMine : styles.msgTheirs]}>
            <View style={styles.rowBetween}>
              <Text style={[styles.author, m.mine && styles.mineText]}>{m.author}</Text>
              <Text style={[styles.time, m.mine && styles.mineText]}>{formatClock(new Date(m.created_at))}</Text>
            </View>
            <Text style={[styles.msgText, m.mine && styles.mineText]}>{m.text}</Text>
            {!m.mine ? (
              <Pressable onPress={() => flag(m.id)} accessibilityRole="button" hitSlop={8}>
                <Text style={styles.flag}>⚑ {t('flag')}</Text>
              </Pressable>
            ) : null}
          </View>
        ))}
      </ScrollView>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <View style={styles.inputRow}>
        <TextInput
          value={text}
          onChangeText={setText}
          placeholder={t('writeMessage')}
          placeholderTextColor={colors.inkSoft}
          style={styles.input}
          maxLength={500}
          returnKeyType="send"
          onSubmitEditing={send}
        />
        <Pressable onPress={send} disabled={sending || !text.trim()} style={[styles.sendBtn, !text.trim() && styles.off]}>
          <Text style={styles.sendText}>➤</Text>
        </Pressable>
      </View>
    </View>
  );
}

function EventForm({ onCreated }: { onCreated: (e: CommunityEvent) => void }) {
  const { profile, t } = useApp();
  const [title, setTitle] = useState('');
  const [place, setPlace] = useState(profile?.home_name ?? '');
  const [description, setDescription] = useState('');
  const [kind, setKind] = useState<(typeof KINDS)[number]>('meeting');
  const [when, setWhen] = useState(() => nextRoundHour(24));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    if (title.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      onCreated(await api.createEvent({ title: title.trim(), description, kind, place_name: place, starts_at: when.toISOString() }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('noConnection'));
    } finally {
      setBusy(false);
    }
  };

  const shift = (ms: number) => setWhen((w) => new Date(Math.max(Date.now() + HOUR, w.getTime() + ms)));

  return (
    <Card>
      <SectionTitle>{t('newEvent')}</SectionTitle>
      <Field label={t('eventTitle')} value={title} onChangeText={setTitle} maxLength={120} />
      <Field label={t('eventPlace')} value={place} onChangeText={setPlace} maxLength={120} />
      <Field label={t('eventDescription')} value={description} onChangeText={setDescription} maxLength={1000} multiline />
      <View style={styles.kinds}>
        {KINDS.map((k) => (
          <Choice key={k} label={t(`kind_${k}` as StringKey)} selected={kind === k} onPress={() => setKind(k)} />
        ))}
      </View>
      <Text style={styles.label}>{t('eventWhen')}</Text>
      <Text style={styles.when}>{whenLabel(when.toISOString())}</Text>
      <View style={styles.row}>
        <BigButton label={t('minusHour')} onPress={() => shift(-HOUR)} color={colors.line} textColor={colors.ink} style={styles.flex} />
        <BigButton label={t('plusHour')} onPress={() => shift(HOUR)} color={colors.line} textColor={colors.ink} style={styles.flex} />
        <BigButton label={t('plusDay')} onPress={() => shift(24 * HOUR)} color={colors.line} textColor={colors.ink} style={styles.flex} />
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <BigButton label={t('createEvent')} icon="📅" onPress={create} busy={busy} disabled={title.trim().length < 3} />
    </Card>
  );
}

export default function CommunityScreen() {
  const { profile, t } = useApp();
  const [tab, setTab] = useState<'chat' | 'events'>('chat');
  const [events, setEvents] = useState<CommunityEvent[]>([]);
  const [openEvent, setOpenEvent] = useState<CommunityEvent | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [offline, setOffline] = useState(false);

  const loadEvents = useCallback(async () => {
    try {
      setEvents(await api.events());
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      if (tab === 'events') void loadEvents();
    }, [tab, loadEvents]),
  );

  const toggleRsvp = async (ev: CommunityEvent) => {
    try {
      const updated = await api.rsvp(ev.id, !ev.going);
      setEvents((prev) => prev.map((e) => (e.id === ev.id ? updated : e)));
      if (openEvent?.id === ev.id) setOpenEvent(updated);
    } catch {
      setOffline(true);
    }
  };

  if (!profile) return null;
  if (!profile.token) {
    return (
      <Screen title={t('tabCommunity')}>
        <Banner tone="warn" icon="⚠" text={t('notRegistered')} />
      </Screen>
    );
  }

  return (
    <Screen title={t('tabCommunity')} scroll={!(tab === 'chat' || openEvent)}>
      <View style={styles.tabs}>
        <Choice label={`💬 ${t('harbourChat')}`} selected={tab === 'chat'} onPress={() => { setTab('chat'); setOpenEvent(null); }} />
        <Choice label={`📅 ${t('events')}`} selected={tab === 'events'} onPress={() => setTab('events')} />
      </View>
      {offline ? <Banner tone="warn" icon="📴" text={t('noConnection')} /> : null}

      {tab === 'chat' ? <ChatPanel channel="harbour" /> : null}

      {tab === 'events' && openEvent ? (
        <>
          <Card>
            <Text style={styles.evTitle}>{openEvent.title}</Text>
            <Text style={styles.evMeta}>
              {whenLabel(openEvent.starts_at)} · {openEvent.place_name}
            </Text>
            <BigButton label={t('closeChat')} icon="‹" onPress={() => setOpenEvent(null)} color={colors.line} textColor={colors.ink} />
          </Card>
          <ChatPanel channel={openEvent.channel} />
        </>
      ) : null}

      {tab === 'events' && !openEvent ? (
        <>
          {showForm ? (
            <EventForm
              onCreated={(ev) => {
                setShowForm(false);
                setEvents((prev) => [...prev, ev].sort((a, b) => a.starts_at.localeCompare(b.starts_at)));
              }}
            />
          ) : (
            <BigButton label={t('newEvent')} icon="➕" onPress={() => setShowForm(true)} />
          )}
          {events.length === 0 && !offline ? <Text style={styles.small}>{t('noEvents')}</Text> : null}
          {events.map((ev) => (
            <Card key={ev.id}>
              <View style={styles.rowBetween}>
                <Text style={styles.evKind}>{t(`kind_${ev.kind}` as StringKey)}</Text>
                <Text style={styles.small}>{t('goingCount', { n: ev.going_count })}</Text>
              </View>
              <Text style={styles.evTitle}>{ev.title}</Text>
              <Text style={styles.evMeta}>
                🕓 {whenLabel(ev.starts_at)}
                {ev.place_name ? `  📍 ${ev.place_name}` : ''}
                {ev.distance_km !== null ? ` (${t('kmAway', { n: ev.distance_km })})` : ''}
              </Text>
              {ev.description ? <Text style={styles.evDesc}>{ev.description}</Text> : null}
              {ev.organiser ? <Text style={styles.small}>{t('organiser', { name: ev.organiser })}</Text> : null}
              <View style={styles.row}>
                <BigButton
                  label={ev.going ? `✔ ${t('going')}` : t('imGoing')}
                  onPress={() => toggleRsvp(ev)}
                  color={ev.going ? colors.safe : colors.sea}
                  style={styles.flex}
                />
                <BigButton
                  label={t('eventChat')}
                  icon="💬"
                  onPress={() => setOpenEvent(ev)}
                  color={colors.line}
                  textColor={colors.ink}
                  style={styles.flex}
                />
              </View>
            </Card>
          ))}
        </>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  tabs: { flexDirection: 'row', gap: 8, marginBottom: 4 },
  row: { flexDirection: 'row', gap: 8, marginTop: 8 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  chat: { flex: 1, minHeight: 360, gap: 8, paddingBottom: 90 },
  chatScroll: { flex: 1 },
  chatBody: { gap: 8, paddingVertical: 4 },
  msg: { maxWidth: '88%', borderRadius: 14, paddingHorizontal: 12, paddingVertical: 8, gap: 2 },
  msgMine: { alignSelf: 'flex-end', backgroundColor: colors.sea },
  msgTheirs: { alignSelf: 'flex-start', backgroundColor: colors.card, borderWidth: 1, borderColor: colors.line },
  author: { fontSize: 14, fontWeight: '800', color: colors.ink },
  time: { fontSize: 12, color: colors.inkSoft },
  msgText: { fontSize: 17, lineHeight: 24, color: colors.ink },
  mineText: { color: colors.white },
  flag: { fontSize: 12, color: colors.inkSoft, marginTop: 2 },
  inputRow: { flexDirection: 'row', gap: 8 },
  input: {
    flex: 1, minHeight: TOUCH, borderWidth: 2, borderColor: colors.line, borderRadius: 12,
    paddingHorizontal: 14, fontSize: 17, color: colors.ink, backgroundColor: colors.white,
  },
  sendBtn: { width: TOUCH + 4, minHeight: TOUCH, borderRadius: 12, backgroundColor: colors.sea, alignItems: 'center', justifyContent: 'center' },
  sendText: { fontSize: 24, color: colors.white, fontWeight: '900' },
  off: { opacity: 0.4 },
  error: { fontSize: 14, fontWeight: '700', color: colors.unsafe, textAlign: 'center' },
  small: { fontSize: 14, color: colors.inkSoft },
  label: { fontSize: 15, fontWeight: '700', color: colors.inkSoft, marginTop: 6 },
  when: { fontSize: 22, fontWeight: '900', color: colors.ink },
  kinds: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginVertical: 6 },
  evKind: { fontSize: 13, fontWeight: '800', color: colors.sea, textTransform: 'uppercase' },
  evTitle: { fontSize: 20, fontWeight: '900', color: colors.ink },
  evMeta: { fontSize: 15, fontWeight: '600', color: colors.ink, marginTop: 2 },
  evDesc: { fontSize: 15, color: colors.ink, marginTop: 4, lineHeight: 21 },
});
