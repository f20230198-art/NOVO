import type { SeaLayer } from '../components/LeafletMap';
import { getBaseUrl } from './api';

/** `/forecast/grid`: wave and wind over the sea around a harbour, for drawing the map only.
 * It carries no verdict; the verdict comes from the advisor (risk engine). */
export type SeaGrid = {
  center: { lat: number; lon: number };
  scenario: string;
  synthetic: boolean;
  stale: boolean;
  fetched_at: string;
  utc_offset_seconds: number;
  times: string[];
  points: {
    lat: number;
    lon: number;
    wave: (number | null)[];
    wave_dir: (number | null)[];
    wind: (number | null)[];
    wind_dir: (number | null)[];
    /** Charted depth, m. Null when unknown (no network for the depth service, or an old cache). */
    depth?: number | null;
  }[];
};

export async function fetchSeaGrid(lat: number, lon: number): Promise<SeaGrid> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const resp = await fetch(`${getBaseUrl()}/forecast/grid?lat=${lat}&lon=${lon}`, { signal: controller.signal });
    if (!resp.ok) throw new Error(`sea grid ${resp.status}`);
    return (await resp.json()) as SeaGrid;
  } finally {
    clearTimeout(timer);
  }
}

/** Index of the grid hour that contains `when` (clamped to the grid). */
export function gridHourIndex(grid: SeaGrid, when: Date): number {
  const ms = when.getTime();
  let best = 0;
  grid.times.forEach((t, i) => {
    if (new Date(t).getTime() <= ms) best = i;
  });
  return best;
}

/** Smallest spacing between grid points, in degrees. */
function gridStep(grid: SeaGrid): number {
  const lats = [...new Set(grid.points.map((p) => p.lat))].sort((a, b) => a - b);
  let step = Infinity;
  for (let i = 1; i < lats.length; i++) step = Math.min(step, lats[i] - lats[i - 1]);
  return Number.isFinite(step) && step > 0 ? step : 0.08;
}

export function seaLayerAt(grid: SeaGrid, hour: number): SeaLayer {
  const step = gridStep(grid);
  return {
    step,
    points: grid.points.map((p) => ({
      lat: p.lat,
      lon: p.lon,
      wave: p.wave[hour] ?? null,
      waveDir: p.wave_dir[hour] ?? null,
      wind: p.wind[hour] ?? null,
      windDir: p.wind_dir[hour] ?? null,
      depth: p.depth ?? null,
    })),
  };
}

/** Range over the sea at one hour, for the legend. */
export function seaSummary(layer: SeaLayer) {
  const waves = layer.points.map((p) => p.wave).filter((v): v is number => v !== null);
  const winds = layer.points.map((p) => p.wind).filter((v): v is number => v !== null);
  const depths = layer.points.map((p) => p.depth ?? null).filter((v): v is number => v !== null);
  return {
    waveMin: waves.length ? Math.min(...waves) : null,
    waveMax: waves.length ? Math.max(...waves) : null,
    windMax: winds.length ? Math.max(...winds) : null,
    depthMin: depths.length ? Math.min(...depths) : null,
    depthMax: depths.length ? Math.max(...depths) : null,
  };
}
