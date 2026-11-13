import { useRouter } from 'expo-router';
import { Tabs } from 'expo-router/js-tabs';
import React, { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { SosButton } from '../../components/SosButton';
import { useApp } from '../../lib/store';
import { colors } from '../../lib/theme';

function icon(glyph: string) {
  return ({ focused }: { focused: boolean }) => <Text style={[styles.icon, { opacity: focused ? 1 : 0.55 }]}>{glyph}</Text>;
}

export default function TabsLayout() {
  const { profile, t } = useApp();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  useEffect(() => {
    if (!profile) router.replace('/onboarding');
  }, [profile, router]);

  if (!profile) return <View style={styles.flex} />;

  const barHeight = 66 + insets.bottom;
  return (
    <View style={styles.flex}>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: colors.ink,
          tabBarInactiveTintColor: colors.inkSoft,
          tabBarStyle: { height: barHeight, paddingBottom: insets.bottom + 6, paddingTop: 6 },
          tabBarLabelStyle: { fontSize: 11, fontWeight: '700' },
        }}
      >
        <Tabs.Screen name="index" options={{ title: t('tabHome'), tabBarIcon: icon('🏠') }} />
        <Tabs.Screen name="assistant" options={{ title: t('tabAssistant'), tabBarIcon: icon('🎙') }} />
        <Tabs.Screen name="trip" options={{ title: t('tabTrip'), tabBarIcon: icon('⛵') }} />
        <Tabs.Screen name="community" options={{ title: t('tabCommunity'), tabBarIcon: icon('👥') }} />
        <Tabs.Screen name="watch" options={{ title: t('tabWatch'), tabBarIcon: icon('⚠️') }} />
        <Tabs.Screen name="profile" options={{ title: t('tabProfile'), tabBarIcon: icon('👤') }} />
      </Tabs>
      {/* SOS floats above every tab. */}
      <SosButton bottom={barHeight + 12} />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.bg },
  icon: { fontSize: 24 },
});
