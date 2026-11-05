/** Expression builders for the walking-time flood and the planner columns (pure: no map import). */
export type Expression = unknown[];

function round(n: number, digits = 3): number {
  const f = 10 ** digits;
  return Math.round(n * f) / f;
}

/** Streets reached up to minute `t`: ['<=', ['get','t'], t]. */
export function floodFilter(t: number): Expression {
  return ['<=', ['get', 't'], round(t)];
}

/** The bright "front": buckets within the last `windowMin` minutes before the clock. */
export function frontFilter(t: number, windowMin = 0.75): Expression {
  return ['all', ['<=', ['get', 't'], round(t)], ['>', ['get', 't'], round(t - windowMin)]];
}

/** Time ramp near -> far (cyan -> violet) as a MapLibre expression on the bucket property `t`. */
export function timeRamp(maxMin: number, near: string, far: string): Expression {
  return ['interpolate', ['linear'], ['get', 't'], 0, near, Math.max(1, maxMin), far];
}

/** Clock value (minutes) for a flood that spans `maxMin` minutes in `durationMs` of screen time. */
export function floodClock(elapsedMs: number, durationMs: number, maxMin: number): number {
  if (durationMs <= 0) return maxMin;
  return Math.min(maxMin, (elapsedMs / durationMs) * maxMin);
}

/** A facility lights up when the front has reached it. */
export function isReached(facilityMinutes: number, clockMin: number): boolean {
  return clockMin >= facilityMinutes;
}

/** Height of a planner column while animating from before to after (p = 0..1). */
export function columnHeight(before: number, after: number, p: number, scale: number): number {
  return (before * (1 - p) + after * p) * scale;
}

/** Blend of two feature properties: before * (1 - p) + after * p. */
export function blendExpression(
  p: number,
  before = 'unmet_before',
  after = 'unmet_after',
): Expression {
  return ['+', ['*', ['get', before], round(1 - p, 4)], ['*', ['get', after], round(p, 4)]];
}

/** The same blend as a MapLibre expression, driven by the clock through `p`. */
export function columnHeightExpression(
  p: number,
  scale: number,
  before = 'unmet_before',
  after = 'unmet_after',
): Expression {
  return ['*', blendExpression(p, before, after), scale];
}

/**
 * `line-gradient` of a route drawn up to progress `p` (0..1): solid colour up to p, transparent after.
 * Stops must strictly increase, so the edge cases are written out.
 */
export function routeGradient(p: number, color: string): Expression {
  const clear = 'rgba(26,115,232,0)';
  const base: Expression = ['interpolate', ['linear'], ['line-progress']];
  if (p <= 0.0001) return [...base, 0, clear, 1, clear];
  if (p >= 0.9999) return [...base, 0, color, 1, color];
  const edge = round(p, 4);
  return [...base, 0, color, edge, color, round(edge + 0.0001, 4), clear, 1, clear];
}
