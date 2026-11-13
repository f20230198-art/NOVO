import { useRouter } from 'expo-router';
import { Tabs } from 'expo-router/js-tabs';
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon, type IconName } from '../../components/art';
import { SimulationModal } from '../../components/SimulationModal';
import { SosButton } from '../../components/SosButton';
import { useApp } from '../../lib/store';
import { colors } from '../../lib/theme';

function icon(name: IconName) {
  return ({ focused }: { focused: boolean }) => (
    <View style={[styles.icon, focused && styles.iconOn]}>
      <Icon name={name} size={24} color={focused ? colors.white : colors.inkSoft} weight={focused ? 2.6 : 2.2} />
    </View>
  );
}

export default function TabsLayout() {
  const { profile, family, t } = useApp();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  useEffect(() => {
    if (family) router.replace('/family');
    else if (!profile) router.replace('/onboarding');
  }, [profile, family, router]);

  if (!profile || family) return <View style={styles.flex} />;

  const barHeight = 74 + insets.bottom;
  return (
    <View style={styles.flex}>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: colors.ink,
          tabBarInactiveTintColor: colors.inkSoft,
          tabBarStyle: {
            height: barHeight, paddingBottom: insets.bottom + 6, paddingTop: 8,
            backgroundColor: colors.card, borderTopWidth: 3, borderTopColor: colors.ink, elevation: 0,
          },
          tabBarLabelStyle: { fontSize: 12, fontWeight: '800', marginTop: 4 },
        }}
      >
        <Tabs.Screen name="index" options={{ title: t('tabHome'), tabBarIcon: icon('boat') }} />
        <Tabs.Screen name="assistant" options={{ title: t('tabAssistant'), tabBarIcon: icon('mic') }} />
        <Tabs.Screen name="trip" options={{ title: t('tabTrip'), tabBarIcon: icon('sail') }} />
        <Tabs.Screen name="community" options={{ title: t('tabCommunity'), tabBarIcon: icon('people') }} />
        <Tabs.Screen name="watch" options={{ title: t('tabWatch'), tabBarIcon: icon('flag') }} />
        <Tabs.Screen name="profile" options={{ title: t('tabProfile'), tabBarIcon: icon('person') }} />
      </Tabs>
      {/* SOS floats above every tab. */}
      <SosButton bottom={barHeight + 12} />
      {/* Simulation pop-up: long-press the title on Home or Profile. */}
      <SimulationModal />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.bg },
  icon: { width: 52, height: 30, borderRadius: 4, alignItems: 'center', justifyContent: 'center' },
  iconOn: { backgroundColor: colors.sea },
});
