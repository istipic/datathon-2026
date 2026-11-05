/** Easing functions: input and output are progress values in 0..1. */
export type Ease = (t: number) => number;

export const clamp01 = (t: number): number => (t < 0 ? 0 : t > 1 ? 1 : t);
export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

export const linear: Ease = (t) => clamp01(t);
export const easeOutCubic: Ease = (t) => 1 - (1 - clamp01(t)) ** 3;
export const easeInOutCubic: Ease = (t) => {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
};
export const easeOutExpo: Ease = (t) => {
  const x = clamp01(t);
  return x === 1 ? 1 : 1 - 2 ** (-10 * x);
};
/** Slight overshoot, for small "pops" only. */
export const easeOutBack: Ease = (t) => {
  const x = clamp01(t);
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2;
};

export const EASINGS = { linear, easeOutCubic, easeInOutCubic, easeOutExpo, easeOutBack } as const;
