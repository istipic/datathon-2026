/**
 * One shared requestAnimationFrame loop for every map animation.
 *
 * - Time based: subscribers get `(now, dt)` in milliseconds from the frame timestamp, so the speed is the
 *   same at 60 and 144 Hz.
 * - Runs only while there is a subscriber, the tab is visible, a map is on screen and the user does not
 *   prefer reduced motion. It starts and stops itself.
 * - Dev builds expose `window.__blizuAnim = { frames, running }` for the end-to-end tests.
 */
export type Tick = (now: number, dt: number) => void;

export interface ClockEnv {
  raf: (cb: (t: number) => void) => number;
  caf: (id: number) => void;
}

export interface Clock {
  /** Registers a subscriber; returns the unsubscribe function. */
  subscribe(fn: Tick): () => void;
  /** Set from `document.hidden` / visibilitychange. */
  setHidden(hidden: boolean): void;
  /** Set from an IntersectionObserver on the map container. */
  setOnScreen(onScreen: boolean): void;
  /** Set from the `prefers-reduced-motion` media query. */
  setReducedMotion(reduced: boolean): void;
  readonly running: boolean;
  readonly frames: number;
  readonly subscribers: number;
}

/** The loop must run only when all of these hold (pure, tested). */
export function shouldRun(state: {
  subscribers: number;
  hidden: boolean;
  onScreen: boolean;
  reduced: boolean;
}): boolean {
  return state.subscribers > 0 && !state.hidden && state.onScreen && !state.reduced;
}

export function createClock(env?: Partial<ClockEnv>, expose = false): Clock {
  const raf = env?.raf ?? ((cb) => requestAnimationFrame(cb));
  const caf = env?.caf ?? ((id) => cancelAnimationFrame(id));
  const subs = new Set<Tick>();
  const state = { hidden: false, onScreen: true, reduced: false };
  let handle: number | null = null;
  let last: number | null = null;
  let frames = 0;

  const publish = () => {
    if (expose && typeof window !== 'undefined') {
      (window as unknown as { __blizuAnim?: unknown }).__blizuAnim = {
        frames,
        running: handle !== null,
      };
    }
  };

  function update() {
    const run = shouldRun({ subscribers: subs.size, ...state });
    if (run && handle === null) {
      last = null;
      handle = raf(frame);
    } else if (!run && handle !== null) {
      caf(handle);
      handle = null;
      last = null;
    }
    publish();
  }

  function frame(t: number) {
    handle = null;
    const dt = last === null ? 0 : Math.min(100, t - last); // cap: a long stall must not teleport
    last = t;
    frames += 1;
    for (const fn of [...subs]) fn(t, dt);
    // keep the previous timestamp across consecutive frames; update() would reset it
    if (handle === null && shouldRun({ subscribers: subs.size, ...state })) {
      handle = raf(frame);
      publish();
    } else update();
  }

  publish();
  return {
    subscribe(fn) {
      subs.add(fn);
      update();
      return () => {
        subs.delete(fn);
        update();
      };
    },
    setHidden(hidden) {
      state.hidden = hidden;
      update();
    },
    setOnScreen(onScreen) {
      state.onScreen = onScreen;
      update();
    },
    setReducedMotion(reduced) {
      state.reduced = reduced;
      update();
    },
    get running() {
      return handle !== null;
    },
    get frames() {
      return frames;
    },
    get subscribers() {
      return subs.size;
    },
  };
}

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;
}

/** The app-wide clock, wired to the page visibility and the reduced-motion preference. */
export const clock: Clock = createClock(undefined, import.meta.env.DEV);

if (typeof document !== 'undefined') {
  clock.setHidden(document.hidden);
  document.addEventListener('visibilitychange', () => clock.setHidden(document.hidden));
}
if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
  const query = window.matchMedia('(prefers-reduced-motion: reduce)');
  clock.setReducedMotion(query.matches);
  query.addEventListener?.('change', (e) => clock.setReducedMotion(e.matches));
}
