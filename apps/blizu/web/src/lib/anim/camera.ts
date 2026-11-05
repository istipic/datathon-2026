/** Camera presets and the reduced-motion decision (pure, the map is a minimal interface). */
export interface CameraTarget {
  center: [number, number];
  zoom: number;
  pitch: number;
  bearing: number;
}

export type PresetName = 'overview' | 'street' | 'orbit';

export const PRESETS: Record<PresetName, { zoom: number; pitch: number }> = {
  overview: { zoom: 13, pitch: 0 },
  street: { zoom: 15.6, pitch: 0 },
  orbit: { zoom: 16, pitch: 60 },
};

export function presetTarget(
  name: PresetName,
  center: [number, number],
  bearing = 0,
): CameraTarget {
  return { center, bearing, ...PRESETS[name] };
}

/** Subset of the MapLibre Map API used here, so tests can pass a fake. */
export interface CameraMap {
  flyTo(o: Record<string, unknown>): unknown;
  easeTo(o: Record<string, unknown>): unknown;
  jumpTo(o: Record<string, unknown>): unknown;
}

export type MoveKind = 'jump' | 'fly' | 'ease';

export function moveKind(reduced: boolean, small: boolean): MoveKind {
  return reduced ? 'jump' : small ? 'ease' : 'fly';
}

/**
 * Moves the camera: `jumpTo` when reduced, `easeTo` for small moves, otherwise a `flyTo` with curve 1.42.
 * `essential: false` lets MapLibre itself respect reduced motion as a second line of defence.
 */
export function moveCamera(
  map: CameraMap,
  target: CameraTarget,
  opts: { reduced: boolean; small?: boolean; duration?: number } = { reduced: false },
): MoveKind {
  const kind = moveKind(opts.reduced, Boolean(opts.small));
  const common = {
    center: target.center,
    zoom: target.zoom,
    pitch: target.pitch,
    bearing: target.bearing,
  };
  if (kind === 'jump') map.jumpTo(common);
  else if (kind === 'ease')
    map.easeTo({ ...common, duration: opts.duration ?? 600, essential: false });
  else map.flyTo({ ...common, curve: 1.42, duration: opts.duration ?? 1600, essential: false });
  return kind;
}

/** Orbit: bearing advances 4 degrees per second of real time. */
export const ORBIT_DEG_PER_SEC = 4;
export function orbitBearing(startBearing: number, elapsedMs: number): number {
  return (startBearing + (ORBIT_DEG_PER_SEC * elapsedMs) / 1000) % 360;
}
