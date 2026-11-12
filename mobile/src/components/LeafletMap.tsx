import React, { useEffect, useMemo, useRef } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';

export type MapMarker = {
  id: string;
  lat: number;
  lon: number;
  icon: string; // an emoji
  opacity?: number;
  label?: string;
};

type Props = {
  center: { lat: number; lon: number };
  zoom?: number;
  markers?: MapMarker[];
  /** A movable pin (onboarding / profile harbour picker). */
  pin?: { lat: number; lon: number } | null;
  /** The fisher's own position, drawn as a blue dot. */
  me?: { lat: number; lon: number } | null;
  onPress?: (lat: number, lon: number) => void;
  onMarkerPress?: (id: string) => void;
  style?: StyleProp<ViewStyle>;
};

// Leaflet + OpenStreetMap tiles in a WebView. No API key, works in Expo Go and in
// the APK (react-native-maps would need a Google Maps key for a standalone build).
const HTML = `<!doctype html>
<html><head>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
  html, body, #map { height: 100%; margin: 0; background: #cfe3f1; }
  .pin { font-size: 26px; line-height: 34px; text-align: center; width: 34px; height: 34px;
         background: #fff; border-radius: 17px; border: 2px solid #0B2545; box-shadow: 0 1px 4px rgba(0,0,0,.4); }
  .me { width: 16px; height: 16px; border-radius: 8px; background: #1d6fe0; border: 3px solid #fff; box-shadow: 0 0 0 2px #1d6fe0; }
  #offline { position: absolute; z-index: 999; left: 8px; right: 8px; top: 8px; padding: 8px; border-radius: 8px;
             background: #0B2545; color: #fff; font: 600 14px sans-serif; display: none; }
</style>
</head><body>
<div id="offline">Map needs an internet connection.</div>
<div id="map"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
  var map = null, layer = null, pinMarker = null, meMarker = null, pending = null;
  function post(msg) { if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(msg)); }
  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function init(state) {
    if (typeof L === 'undefined') { document.getElementById('offline').style.display = 'block'; return; }
    map = L.map('map', { zoomControl: true, attributionControl: true }).setView([state.center.lat, state.center.lon], state.zoom);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '&copy; OpenStreetMap' }).addTo(map);
    layer = L.layerGroup().addTo(map);
    map.on('click', function (e) { post({ type: 'press', lat: e.latlng.lat, lon: e.latlng.lng }); });
  }
  function render(state) {
    if (!map) { init(state); if (!map) return; }
    layer.clearLayers();
    (state.markers || []).forEach(function (m) {
      var icon = L.divIcon({ className: '', html: '<div class="pin" style="opacity:' + (m.opacity == null ? 1 : m.opacity) + '">' + esc(m.icon) + '</div>', iconSize: [34, 34], iconAnchor: [17, 17] });
      var marker = L.marker([m.lat, m.lon], { icon: icon }).addTo(layer);
      if (m.label) marker.bindPopup(esc(m.label));
      marker.on('click', function () { post({ type: 'marker', id: m.id }); });
    });
    if (pinMarker) { map.removeLayer(pinMarker); pinMarker = null; }
    if (state.pin) pinMarker = L.marker([state.pin.lat, state.pin.lon]).addTo(map);
    if (meMarker) { map.removeLayer(meMarker); meMarker = null; }
    if (state.me) meMarker = L.marker([state.me.lat, state.me.lon], { icon: L.divIcon({ className: '', html: '<div class="me"></div>', iconSize: [16, 16], iconAnchor: [8, 8] }) }).addTo(map);
    if (state.recenter) map.setView([state.center.lat, state.center.lon], state.zoom);
  }
  window.update = function (state) { pending = state; render(state); };
  post({ type: 'ready' });
</script>
</body></html>`;

export function LeafletMap({ center, zoom = 11, markers, pin, me, onPress, onMarkerPress, style }: Props) {
  // WebView's default type parameter is `undefined`, which collapses its props to `never`.
  const web = useRef<WebView<object>>(null);
  const ready = useRef(false);
  const lastCenter = useRef('');

  const state = useMemo(() => ({ center, zoom, markers: markers ?? [], pin: pin ?? null, me: me ?? null }), [center, zoom, markers, pin, me]);

  const push = () => {
    if (!ready.current) return;
    const centerKey = `${state.center.lat.toFixed(4)},${state.center.lon.toFixed(4)},${state.zoom}`;
    const recenter = centerKey !== lastCenter.current;
    lastCenter.current = centerKey;
    web.current?.injectJavaScript(`window.update(${JSON.stringify({ ...state, recenter })}); true;`);
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(push, [state]);

  const onMessage = (event: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(event.nativeEvent.data) as { type: string; lat?: number; lon?: number; id?: string };
      if (msg.type === 'ready') {
        ready.current = true;
        lastCenter.current = '';
        push();
      } else if (msg.type === 'press' && typeof msg.lat === 'number' && typeof msg.lon === 'number') {
        onPress?.(msg.lat, msg.lon);
      } else if (msg.type === 'marker' && msg.id) {
        onMarkerPress?.(msg.id);
      }
    } catch {
      // ignore anything that is not our own message
    }
  };

  return (
    <View style={[styles.wrap, style]}>
      <WebView<object>
        ref={web}
        originWhitelist={['*']}
        source={{ html: HTML }}
        onMessage={onMessage}
        javaScriptEnabled
        domStorageEnabled
        scrollEnabled={false}
        nestedScrollEnabled
        style={styles.web}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { height: 260, borderRadius: 16, overflow: 'hidden', borderWidth: 1, borderColor: '#C9D6E2' },
  web: { flex: 1, backgroundColor: '#cfe3f1' },
});
