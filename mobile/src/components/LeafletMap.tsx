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

/** Sea state at one grid point for one hour. Directions are where it comes FROM, in degrees. */
export type SeaPoint = {
  lat: number;
  lon: number;
  wave: number | null; // m
  waveDir: number | null;
  wind: number | null; // km/h
  windDir: number | null;
  depth?: number | null; // charted depth, m (positive down)
};

/** Sea points on a regular grid `step` degrees apart. Points on land are simply absent. */
export type SeaLayer = { step: number; points: SeaPoint[] };

/** What the sea layer shows. Each mode draws only its own thing, so the map stays readable. */
export type SeaMode = 'waves' | 'wind' | 'depth' | 'off';

/**
 * Blue scales, light (low) to deep (high): [value, r, g, b, alpha]. Shared by the map canvas
 * and the legend. Only blues: green/amber/red mean the verdict, which depends on the boat.
 */
export const BLUE_SCALES = {
  waves: [
    [0, 205, 235, 250, 0.16],
    [0.5, 150, 205, 240, 0.3],
    [1, 95, 165, 225, 0.42],
    [1.5, 50, 120, 205, 0.52],
    [2.5, 20, 75, 170, 0.62],
    [3.5, 8, 40, 115, 0.72],
  ],
  // Depth grows fast off the shelf, so the stops are spaced for the shallow water fishers use.
  depth: [
    [0, 215, 240, 252, 0.3],
    [10, 165, 215, 243, 0.42],
    [30, 110, 178, 230, 0.52],
    [60, 62, 132, 210, 0.6],
    [200, 25, 80, 170, 0.68],
    [1000, 8, 35, 105, 0.78],
  ],
} as const satisfies Record<'waves' | 'depth', readonly (readonly number[])[]>;

type Props = {
  center: { lat: number; lon: number };
  zoom?: number;
  markers?: MapMarker[];
  /** Wave texture and wind arrows drawn on the water. */
  sea?: SeaLayer | null;
  /** Which sea layer to draw (default waves). */
  seaMode?: SeaMode;
  /** Change this number to fly back to `center` after the fisher has panned away. */
  recenterKey?: number;
  /** Fill the parent instead of the default 260 dp card. */
  fill?: boolean;
  /** Hide the +/- buttons (pinch still zooms). */
  hideZoomButtons?: boolean;
  /** Lift the attribution above something covering the bottom of the map, in dp. */
  bottomInset?: number;
  /** Stop the wave animation, e.g. while the screen is not in view. */
  paused?: boolean;
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
  .sea { transition: opacity .25s ease; }
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
    map = L.map('map', { zoomControl: !state.hideZoomButtons, attributionControl: true }).setView([state.center.lat, state.center.lon], state.zoom);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '&copy; OpenStreetMap' }).addTo(map);
    layer = L.layerGroup().addTo(map);
    map.on('click', function (e) { post({ type: 'press', lat: e.latlng.lat, lon: e.latlng.lng }); });
    // The WebView changes size: it starts at 0 x 0, a hidden tab can shrink to 0, the keyboard
    // shrinks the window. Leaflet keeps its top-left corner on a resize, so the view would creep
    // a little further every time. Ignore zero sizes, and keep the centre where it was.
    var el = document.getElementById('map'), sized = el.clientHeight > 0;
    if (window.ResizeObserver) new ResizeObserver(function () {
      if (!el.clientHeight || !el.clientWidth) return; // hidden: leave the map alone
      if (!sized) { sized = true; map.invalidateSize({ pan: false }); map.setView([pending.center.lat, pending.center.lon], pending.zoom, { animate: false }); return; }
      var keep = map.getCenter();
      map.invalidateSize({ pan: false });
      map.setView(keep, map.getZoom(), { animate: false });
    }).observe(el);
  }

  // ---- Sea layer on a canvas between the tiles and the markers. One mode at a time:
  // waves = blue by wave height + drifting crests, wind = arrows, depth = blue by charted depth.
  var PAD = 140, CELL = 26;
  var sea = null, seaKey = '', mode = 'waves', canvas = null, ctx = null, tint = null, cells = [], arrows = [];
  var frame = 0, lastDraw = 0, paused = false, cw = 0, ch = 0;
  var SCALES = ${JSON.stringify(BLUE_SCALES)};
  function blue(STOPS, h) {
    if (h <= STOPS[0][0]) return STOPS[0].slice(1);
    for (var i = 1; i < STOPS.length; i++) {
      if (h <= STOPS[i][0]) {
        var a = STOPS[i - 1], b = STOPS[i], k = (h - a[0]) / (b[0] - a[0]);
        return [a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k, a[3] + (b[3] - a[3]) * k, a[4] + (b[4] - a[4]) * k];
      }
    }
    return STOPS[STOPS.length - 1].slice(1);
  }
  function windColour(s) { return s < 15 ? '#4A6FA5' : s < 30 ? '#13315C' : s < 45 ? '#5A189A' : '#8E0E8A'; }
  function rad(d) { return d * Math.PI / 180; }

  function ensureSea() {
    if (canvas) return;
    var pane = map.createPane('sea');
    pane.style.zIndex = 450; pane.style.pointerEvents = 'none';
    canvas = L.DomUtil.create('canvas', 'sea', pane);
    ctx = canvas.getContext('2d');
    tint = document.createElement('canvas');
    map.on('moveend resize', rebuild);
    map.on('zoomstart', function () { canvas.style.opacity = 0; });
    map.on('zoomend', function () { rebuild(); canvas.style.opacity = 1; });
  }

  // Work out, once per map move, what to draw in each screen cell. The per-frame loop then only strokes.
  function rebuild() {
    if (!canvas) return;
    cells = []; arrows = [];
    var size = map.getSize(), dpr = Math.min(window.devicePixelRatio || 1, 2);
    cw = size.x + 2 * PAD; ch = size.y + 2 * PAD;
    canvas.width = cw * dpr; canvas.height = ch * dpr;
    canvas.style.width = cw + 'px'; canvas.style.height = ch + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([-PAD, -PAD]));
    var pts = sea && mode !== 'off' ? sea.points : [];
    if (!pts.length) { ctx.clearRect(0, 0, cw, ch); tint.width = tint.height = 0; return; }

    var step = sea.step, reach = step * 0.8, soft = step * 0.3;
    var cols = Math.ceil(cw / CELL), rows = Math.ceil(ch / CELL);
    var shade = mode === 'waves' || mode === 'depth', key = mode === 'depth' ? 'depth' : 'wave';
    tint.width = shade ? cols : 0; tint.height = shade ? rows : 0;
    var tctx = shade ? tint.getContext('2d') : null, img = shade ? tctx.createImageData(cols, rows) : null;
    for (var r = 0; shade && r < rows; r++) {
      for (var c = 0; c < cols; c++) {
        var x = (c + 0.5) * CELL, y = (r + 0.5) * CELL;
        var ll = map.containerPointToLatLng([x - PAD, y - PAD]);
        var kx = Math.cos(rad(ll.lat)), near = 1e9, sw = 0, sh = 0, sx = 0, sy = 0;
        for (var i = 0; i < pts.length; i++) {
          var p = pts[i];
          if (p[key] == null) continue;
          var dy = p.lat - ll.lat, dx = (p.lon - ll.lng) * kx, d2 = dx * dx + dy * dy;
          if (d2 > 4 * step * step) continue;
          var d = Math.sqrt(d2); if (d < near) near = d;
          var w = 1 / (d2 + step * step * 0.05);
          sw += w; sh += w * p[key];
          if (p.waveDir != null) { sx += w * Math.sin(rad(p.waveDir)); sy += w * Math.cos(rad(p.waveDir)); }
        }
        if (!sw || near > reach) continue; // land, or outside the forecast grid
        var h = sh / sw, edge = Math.min(1, (reach - near) / soft), col = blue(SCALES[mode], h), o = (r * cols + c) * 4;
        img.data[o] = col[0]; img.data[o + 1] = col[1]; img.data[o + 2] = col[2]; img.data[o + 3] = 255 * col[3] * edge;
        if (mode !== 'waves') continue; // crests only on the wave layer
        // Waves travel away from where they come from. Screen y points south.
        var from = (sx || sy) ? Math.atan2(sx, sy) : rad(250);
        var seed = (Math.sin(c * 12.9898 + r * 78.233) * 43758.5453) % 1; if (seed < 0) seed += 1;
        if (h < 0.5 && seed > 0.55) continue; // a calm sea gets fewer crests
        cells.push({ x: x, y: y, h: h, tx: -Math.sin(from), ty: Math.cos(from), seed: seed, edge: edge });
      }
    }
    if (shade) tctx.putImageData(img, 0, 0);
    if (mode !== 'wind') { draw(performance.now()); return; }

    // One wind arrow per grid point, thinned out when zoomed far enough that they would touch.
    var a0 = map.latLngToContainerPoint([pts[0].lat, pts[0].lon]), a1 = map.latLngToContainerPoint([pts[0].lat + step, pts[0].lon]);
    var stride = Math.max(1, Math.ceil(46 / Math.max(1, Math.abs(a1.y - a0.y))));
    var lat0 = 1e9, lon0 = 1e9;
    pts.forEach(function (p) { if (p.lat < lat0) lat0 = p.lat; if (p.lon < lon0) lon0 = p.lon; });
    pts.forEach(function (p) {
      if (p.wind == null || p.windDir == null) return;
      var ri = Math.round((p.lat - lat0) / step), ci = Math.round((p.lon - lon0) / step);
      if (ri % stride || ci % stride) return;
      var q = map.latLngToContainerPoint([p.lat, p.lon]), to = rad(p.windDir + 180);
      arrows.push({ x: q.x + PAD, y: q.y + PAD, dx: Math.sin(to), dy: -Math.cos(to), s: p.wind });
    });
    draw(performance.now());
  }

  function draw(now) {
    var t = now / 1000;
    ctx.clearRect(0, 0, cw, ch);
    ctx.imageSmoothingEnabled = true;
    if (tint.width) ctx.drawImage(tint, 0, 0, tint.width, tint.height, 0, 0, tint.width * CELL, tint.height * CELL);

    // Crests: short curved strokes drifting the way the waves run. Higher sea: more, longer, bolder, faster.
    ctx.lineCap = 'round';
    for (var i = 0; i < cells.length; i++) {
      var c = cells[i], k = Math.min(c.h, 4);
      var phase = (t * (0.10 + 0.06 * k) + c.seed) % 1, fade = Math.sin(Math.PI * phase) * c.edge;
      var cx = c.x + c.tx * (phase - 0.5) * CELL * 1.3, cy = c.y + c.ty * (phase - 0.5) * CELL * 1.3;
      var half = 4 + 3 * k, bulge = 1.5 + 1.6 * k, nx = -c.ty, ny = c.tx;
      ctx.beginPath();
      ctx.moveTo(cx - nx * half, cy - ny * half);
      ctx.quadraticCurveTo(cx + c.tx * bulge, cy + c.ty * bulge, cx + nx * half, cy + ny * half);
      ctx.strokeStyle = 'rgba(255,255,255,' + (Math.min(0.9, 0.35 + 0.18 * k) * fade).toFixed(3) + ')';
      ctx.lineWidth = Math.min(2.8, 1 + 0.5 * k);
      ctx.stroke();
    }

    // Wind: an arrow pointing where the wind is going, longer and darker as it strengthens.
    for (var j = 0; j < arrows.length; j++) {
      var a = arrows[j], len = Math.min(42, 14 + a.s * 0.5), wdt = Math.min(4.5, 2 + a.s / 22);
      var slide = Math.sin(t * 1.6 + j) * 2.5, head = 5 + wdt * 1.6;
      var x0 = a.x - a.dx * (len / 2 - slide), y0 = a.y - a.dy * (len / 2 - slide);
      var x1 = a.x + a.dx * (len / 2 + slide), y1 = a.y + a.dy * (len / 2 + slide);
      var px = -a.dy, py = a.dx;
      for (var pass = 0; pass < 2; pass++) { // white halo first, so arrows read on any sea colour
        ctx.strokeStyle = pass ? windColour(a.s) : 'rgba(255,255,255,0.9)';
        ctx.lineWidth = pass ? wdt : wdt + 2.5;
        ctx.lineJoin = 'round';
        ctx.beginPath();
        ctx.moveTo(x0, y0); ctx.lineTo(x1, y1);
        ctx.moveTo(x1 - a.dx * head + px * head * 0.6, y1 - a.dy * head + py * head * 0.6);
        ctx.lineTo(x1, y1);
        ctx.lineTo(x1 - a.dx * head - px * head * 0.6, y1 - a.dy * head - py * head * 0.6);
        ctx.stroke();
      }
    }
  }

  // Only waves and wind move. Depth and off are drawn once by rebuild() and cost nothing after.
  function animated() { return mode === 'waves' || mode === 'wind'; }
  function loop(now) {
    frame = 0;
    if (paused || !sea || !sea.points.length || document.hidden || !animated()) return;
    if (now - lastDraw > 40) { lastDraw = now; draw(now); } // about 25 frames a second is plenty
    frame = requestAnimationFrame(loop);
  }
  function setSea(next, key, nextMode, isPaused) {
    paused = !!isPaused;
    var full = key + '|' + nextMode;
    if (full !== seaKey) { seaKey = full; sea = next; mode = nextMode || 'waves'; if (sea) ensureSea(); rebuild(); }
    if (!frame && !paused && sea && animated()) frame = requestAnimationFrame(loop);
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
    var bottoms = document.querySelectorAll('.leaflet-bottom');
    for (var i = 0; i < bottoms.length; i++) bottoms[i].style.bottom = (state.bottomInset || 0) + 'px';
    setSea(state.sea, state.seaKey, state.seaMode, state.paused);
  }
  window.update = function (state) { pending = state; render(state); };
  post({ type: 'ready' });
</script>
</body></html>`;

// A stable id per sea layer object, so the page can tell a new layer from a re-render.
const seaIds = new WeakMap<SeaLayer, string>();
let nextSeaId = 0;
function seaId(layer: SeaLayer): string {
  let id = seaIds.get(layer);
  if (!id) {
    id = String(++nextSeaId);
    seaIds.set(layer, id);
  }
  return id;
}

export function LeafletMap({
  center,
  zoom = 11,
  markers,
  pin,
  me,
  sea,
  seaMode = 'waves',
  recenterKey = 0,
  fill,
  hideZoomButtons,
  bottomInset = 0,
  paused = false,
  onPress,
  onMarkerPress,
  style,
}: Props) {
  // WebView's default type parameter is `undefined`, which collapses its props to `never`.
  const web = useRef<WebView<object>>(null);
  const ready = useRef(false);
  const lastCenter = useRef('');
  // The page only rebuilds the sea layer when this changes, not on every marker update.
  const seaKey = sea ? seaId(sea) : '0';

  const state = useMemo(
    () => ({
      center,
      zoom,
      markers: markers ?? [],
      pin: pin ?? null,
      me: me ?? null,
      sea: sea ?? null,
      seaKey,
      seaMode,
      recenterKey,
      hideZoomButtons: !!hideZoomButtons,
      bottomInset,
      paused,
    }),
    [center, zoom, markers, pin, me, sea, seaKey, seaMode, recenterKey, hideZoomButtons, bottomInset, paused],
  );

  const push = () => {
    if (!ready.current) return;
    const centerKey = `${state.center.lat.toFixed(4)},${state.center.lon.toFixed(4)},${state.zoom},${state.recenterKey}`;
    const recenter = centerKey !== lastCenter.current;
    lastCenter.current = centerKey;
    web.current?.injectJavaScript(`window.update(${JSON.stringify({ ...state, recenter })}); true;`);
  };

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
    <View style={[fill ? styles.fill : styles.wrap, style]}>
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
  fill: { ...StyleSheet.absoluteFill, overflow: 'hidden' },
  web: { flex: 1, backgroundColor: '#cfe3f1' },
});
