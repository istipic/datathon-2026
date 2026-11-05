import { clamp01, linear, type Ease } from './easing';
import type { Clock } from './clock';

/** One animated property: runs from `at` for `duration` ms and receives eased progress 0..1. */
export interface Keyframe {
  at: number;
  duration: number;
  ease?: Ease;
  apply: (p: number) => void;
}

export interface Timeline {
  readonly duration: number;
  /** Applies every keyframe at time `t` (ms from the start); idempotent, so scrubbing works. */
  sample(t: number): void;
}

export function createTimeline(keyframes: Keyframe[]): Timeline {
  const duration = keyframes.reduce((max, k) => Math.max(max, k.at + k.duration), 0);
  return {
    duration,
    sample(t) {
      for (const k of keyframes) {
        const p = k.duration <= 0 ? (t >= k.at ? 1 : 0) : clamp01((t - k.at) / k.duration);
        k.apply((k.ease ?? linear)(p));
      }
    },
  };
}

export interface PlayHandle {
  cancel(): void;
  readonly done: boolean;
}

/**
 * Plays a timeline on the clock. When `reduced` is true the final state is applied immediately and
 * `onDone` fires synchronously: same information, no movement.
 */
export function play(
  clock: Clock,
  timeline: Timeline,
  opts: { reduced: boolean; onDone?: () => void; speed?: number } = { reduced: false },
): PlayHandle {
  let elapsed = 0;
  let done = false;
  let unsubscribe: (() => void) | null = null;
  const finish = () => {
    if (done) return;
    done = true;
    unsubscribe?.();
    opts.onDone?.();
  };
  if (opts.reduced) {
    timeline.sample(timeline.duration);
    finish();
    return { cancel: () => undefined, done: true };
  }
  timeline.sample(0);
  unsubscribe = clock.subscribe((_now, dt) => {
    elapsed += dt * (opts.speed ?? 1);
    timeline.sample(elapsed);
    if (elapsed >= timeline.duration) finish();
  });
  return {
    cancel() {
      if (done) return;
      done = true;
      unsubscribe?.();
    },
    get done() {
      return done;
    },
  };
}

/** Limits how often `fn` runs (default 30 Hz); progress 1 always goes through so the end state is exact. */
export function throttleApply(fn: (p: number) => void, ms = 33): (p: number) => void {
  let last = -Infinity;
  return (p) => {
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    if (p >= 1 || p <= 0 || now - last >= ms) {
      last = now;
      fn(p);
    }
  };
}
