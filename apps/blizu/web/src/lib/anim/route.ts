import { clamp01 } from './easing';

export type Coord = [number, number]; // [lon, lat]

const R = 6_371_008.8;
const rad = (d: number) => (d * Math.PI) / 180;

/** Great-circle distance in metres. */
export function haversine(a: Coord, b: Coord): number {
  const dLat = rad(b[1] - a[1]);
  const dLon = rad(b[0] - a[0]);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Initial bearing from a to b in degrees (0 = north, clockwise). */
export function bearing(a: Coord, b: Coord): number {
  const y = Math.sin(rad(b[0] - a[0])) * Math.cos(rad(b[1]));
  const x =
    Math.cos(rad(a[1])) * Math.sin(rad(b[1])) -
    Math.sin(rad(a[1])) * Math.cos(rad(b[1])) * Math.cos(rad(b[0] - a[0]));
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

export interface RouteGeometry {
  coordinates: Coord[];
  /** cumulative[i] = metres from the start to coordinates[i]. */
  cumulative: number[];
  length: number;
}

export function buildRoute(coordinates: Coord[]): RouteGeometry {
  const cumulative: number[] = [0];
  for (let i = 1; i < coordinates.length; i++) {
    cumulative.push(
      (cumulative[i - 1] as number) +
        haversine(coordinates[i - 1] as Coord, coordinates[i] as Coord),
    );
  }
  return { coordinates, cumulative, length: cumulative[cumulative.length - 1] ?? 0 };
}

/** Index of the segment [i, i+1] that contains distance `d` (clamped). */
function segmentAt(route: RouteGeometry, d: number): number {
  const { cumulative } = route;
  let lo = 0;
  let hi = cumulative.length - 2;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if ((cumulative[mid] as number) <= d) lo = mid;
    else hi = mid - 1;
  }
  return Math.max(0, lo);
}

/** Point at progress p (0..1 of the route length), linear between nodes. */
export function positionAt(route: RouteGeometry, p: number): Coord {
  const pts = route.coordinates;
  if (pts.length === 0) return [0, 0];
  if (pts.length === 1 || route.length === 0) return pts[0] as Coord;
  const d = clamp01(p) * route.length;
  const i = segmentAt(route, d);
  const a = pts[i] as Coord;
  const b = pts[i + 1] as Coord;
  const seg = (route.cumulative[i + 1] as number) - (route.cumulative[i] as number);
  const f = seg === 0 ? 0 : (d - (route.cumulative[i] as number)) / seg;
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
}

/** Direction of travel at progress p, in degrees. */
export function bearingAt(route: RouteGeometry, p: number): number {
  const pts = route.coordinates;
  if (pts.length < 2) return 0;
  const i = segmentAt(route, clamp01(p) * route.length);
  return bearing(pts[i] as Coord, pts[i + 1] as Coord);
}

/**
 * Walking progress after `elapsedMs` of screen time at `speedMps` scaled by a constant time-lapse factor
 * ("ubrzano ×30" in the UI). Honest: the persona's real speed, only the clock is faster.
 */
export function walkProgress(
  route: RouteGeometry,
  elapsedMs: number,
  speedMps: number,
  timelapse: number,
): number {
  if (route.length <= 0) return 1;
  return clamp01(((elapsedMs / 1000) * speedMps * timelapse) / route.length);
}
