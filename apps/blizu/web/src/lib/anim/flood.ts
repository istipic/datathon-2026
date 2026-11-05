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

/** The same blend as a MapLibre expression, driven by the clock through `p`. */
export function columnHeightExpression(p: number, scale: number): Expression {
  return [
    '*',
    [
      '+',
      ['*', ['get', 'unmet_before'], round(1 - p, 4)],
      ['*', ['get', 'unmet_after'], round(p, 4)],
    ],
    scale,
  ];
}
