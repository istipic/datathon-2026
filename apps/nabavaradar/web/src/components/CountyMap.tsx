import { useMemo } from 'react';

type Position = [number, number];
type Ring = Position[];
export interface CountyFeature {
  properties: { nuts3: string; name: string | null };
  geometry: { type: 'Polygon' | 'MultiPolygon'; coordinates: Ring[] | Ring[][] };
}
export interface CountyGeo {
  features: CountyFeature[];
}

/** Sequential indigo ramp (light -> dark); the legend and the table carry the numbers. */
export const RAMP = ['#E0E7FF', '#A5B4FC', '#6366F1', '#4338CA', '#312E81'] as const;
const EMPTY_FILL = '#F1F5F9';
const SCALE = 100;

function polygons(feature: CountyFeature): Ring[][] {
  const g = feature.geometry;
  return g.type === 'Polygon' ? [g.coordinates as Ring[]] : (g.coordinates as Ring[][]);
}

/** Equirectangular projection with cos(latitude) correction -> SVG path strings and the viewBox. */
export function project(geo: CountyGeo): {
  paths: { nuts3: string; name: string; d: string }[];
  width: number;
  height: number;
} {
  let minLon = Infinity;
  let maxLon = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;
  for (const f of geo.features)
    for (const poly of polygons(f))
      for (const ring of poly)
        for (const [lon, lat] of ring) {
          minLon = Math.min(minLon, lon);
          maxLon = Math.max(maxLon, lon);
          minLat = Math.min(minLat, lat);
          maxLat = Math.max(maxLat, lat);
        }
  const kx = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
  const x = (lon: number) => ((lon - minLon) * kx * SCALE).toFixed(1);
  const y = (lat: number) => ((maxLat - lat) * SCALE).toFixed(1);
  const paths = geo.features.map((f) => ({
    nuts3: f.properties.nuts3,
    name: f.properties.name ?? f.properties.nuts3,
    d: polygons(f)
      .map((poly) =>
        poly.map((ring) => `M${ring.map(([lon, lat]) => `${x(lon)},${y(lat)}`).join('L')}Z`).join(''),
      )
      .join(''),
  }));
  return { paths, width: (maxLon - minLon) * kx * SCALE, height: (maxLat - minLat) * SCALE };
}

/** Class breaks (quantiles of the positive values) -> 4 thresholds for 5 classes. */
export function breaks(values: number[]): number[] {
  const positive = values.filter((v) => v > 0).sort((a, b) => a - b);
  if (positive.length === 0) return [];
  return [0.2, 0.4, 0.6, 0.8].map((q) => positive[Math.min(positive.length - 1, Math.floor(q * positive.length))] ?? 0);
}

export function classOf(value: number, thresholds: number[]): number {
  if (value <= 0) return -1;
  let c = 0;
  for (const t of thresholds) if (value > t) c += 1;
  return Math.min(c, RAMP.length - 1);
}

export interface CountyMapProps {
  geo: CountyGeo;
  /** value per NUTS3 code */
  values: Record<string, number>;
  /** noun used in titles, e.g. "dobavljača" */
  unit: string;
  label: string;
}

/** SVG choropleth of the counties (no WebGL: works in jsdom and prints well). */
export function CountyMap({ geo, values, unit, label }: CountyMapProps) {
  const { paths, width, height } = useMemo(() => project(geo), [geo]);
  const thresholds = useMemo(() => breaks(Object.values(values)), [values]);
  const legend = useMemo(() => {
    const edges = [0, ...thresholds];
    return RAMP.map((color, i) => {
      const lo = edges[i] ?? edges[edges.length - 1] ?? 0;
      const hi = thresholds[i];
      return { color, text: hi === undefined ? `više od ${lo}` : i === 0 ? `1–${hi}` : `${lo + 1}–${hi}` };
    });
  }, [thresholds]);

  return (
    <figure>
      <svg
        className="nr-map"
        viewBox={`-5 -5 ${width + 10} ${height + 10}`}
        role="img"
        aria-label={label}
      >
        {paths.map((p) => {
          const value = values[p.nuts3] ?? 0;
          const c = classOf(value, thresholds);
          return (
            <path key={p.nuts3} d={p.d} fill={c < 0 ? EMPTY_FILL : RAMP[c]} data-nuts3={p.nuts3}>
              <title>{`${p.name}: ${value} ${unit}`}</title>
            </path>
          );
        })}
      </svg>
      <figcaption className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span>
          <span className="nr-legend-swatch" style={{ background: EMPTY_FILL }} /> 0
        </span>
        {legend.map((l) => (
          <span key={l.color}>
            <span className="nr-legend-swatch" style={{ background: l.color }} />{' '}
            <span className="num">{l.text}</span>
          </span>
        ))}
        <span className="text-neutral-600">Granice: © EuroGeographics (Eurostat GISCO)</span>
      </figcaption>
    </figure>
  );
}
