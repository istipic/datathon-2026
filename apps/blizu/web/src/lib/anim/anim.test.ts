import { describe, expect, it, vi } from 'vitest';
import route from '../../__fixtures__/2026-11-05_route_starija_skola.json';
import isochrone from '../../__fixtures__/2026-11-05_isochrone_starija.json';
import { moveCamera, moveKind, orbitBearing, presetTarget } from './camera';
import { createClock, shouldRun } from './clock';
import { clamp01, easeInOutCubic, easeOutBack, easeOutCubic, easeOutExpo, linear } from './easing';
import {
  columnHeight,
  columnHeightExpression,
  floodClock,
  floodFilter,
  frontFilter,
  isReached,
} from './flood';
import { bearingAt, buildRoute, haversine, positionAt, walkProgress, type Coord } from './route';
import { initialScene, nextScene, parseScene, threeDAvailable, withScene } from './scene';
import { createTimeline, play } from './timeline';

/** A fake requestAnimationFrame we can step by hand. */
function fakeRaf() {
  let next = 1;
  const pending = new Map<number, (t: number) => void>();
  return {
    raf: (cb: (t: number) => void) => {
      const id = next++;
      pending.set(id, cb);
      return id;
    },
    caf: (id: number) => void pending.delete(id),
    step(t: number) {
      const cbs = [...pending.values()];
      pending.clear();
      for (const cb of cbs) cb(t);
    },
    get pending() {
      return pending.size;
    },
  };
}

describe('easing', () => {
  it('starts at 0, ends at 1 and is monotone', () => {
    for (const ease of [linear, easeOutCubic, easeInOutCubic, easeOutExpo]) {
      expect(ease(0)).toBeCloseTo(0, 6);
      expect(ease(1)).toBeCloseTo(1, 6);
      let prev = -1;
      for (let i = 0; i <= 20; i++) {
        const v = ease(i / 20);
        expect(v).toBeGreaterThanOrEqual(prev);
        prev = v;
      }
    }
    expect(easeOutBack(1)).toBeCloseTo(1, 6);
    expect(Math.max(...[0.5, 0.7, 0.9].map(easeOutBack))).toBeGreaterThan(1); // the small overshoot
    expect(clamp01(-3)).toBe(0);
    expect(clamp01(9)).toBe(1);
  });
});

describe('clock', () => {
  it('runs only with subscribers, visible, on screen and without reduced motion', () => {
    const ok = { subscribers: 1, hidden: false, onScreen: true, reduced: false };
    expect(shouldRun(ok)).toBe(true);
    expect(shouldRun({ ...ok, subscribers: 0 })).toBe(false);
    expect(shouldRun({ ...ok, hidden: true })).toBe(false);
    expect(shouldRun({ ...ok, onScreen: false })).toBe(false);
    expect(shouldRun({ ...ok, reduced: true })).toBe(false);
  });

  it('is time based: dt comes from timestamps, identical at 60 and 144 Hz', () => {
    const total = (hz: number) => {
      const env = fakeRaf();
      const clock = createClock(env);
      let sum = 0;
      clock.subscribe((_n, dt) => (sum += dt));
      const step = 1000 / hz;
      for (let t = 0; t <= 1000 + 1e-6; t += step) env.step(t);
      return sum;
    };
    expect(total(60)).toBeCloseTo(1000, -1);
    expect(total(144)).toBeCloseTo(1000, -1);
  });

  it('pauses when hidden or off screen and resumes, and never runs when reduced', () => {
    const env = fakeRaf();
    const clock = createClock(env);
    const tick = vi.fn();
    const off = clock.subscribe(tick);
    expect(clock.running).toBe(true);
    clock.setHidden(true);
    expect(clock.running).toBe(false);
    expect(env.pending).toBe(0);
    clock.setHidden(false);
    clock.setOnScreen(false);
    expect(clock.running).toBe(false);
    clock.setOnScreen(true);
    expect(clock.running).toBe(true);
    clock.setReducedMotion(true);
    expect(clock.running).toBe(false);
    clock.setReducedMotion(false);
    env.step(0);
    env.step(16);
    expect(tick).toHaveBeenCalledTimes(2);
    off();
    expect(clock.running).toBe(false);
    expect(clock.subscribers).toBe(0);
  });

  it('caps a long stall so nothing teleports', () => {
    const env = fakeRaf();
    const clock = createClock(env);
    const dts: number[] = [];
    clock.subscribe((_n, dt) => dts.push(dt));
    env.step(0);
    env.step(5000);
    expect(dts).toEqual([0, 100]);
  });
});

describe('timeline', () => {
  it('applies eased progress per keyframe and is idempotent when scrubbed', () => {
    const seen: number[] = [];
    const tl = createTimeline([
      { at: 100, duration: 200, apply: (p) => seen.push(p) },
      { at: 0, duration: 0, apply: () => undefined },
    ]);
    expect(tl.duration).toBe(300);
    tl.sample(0);
    tl.sample(200);
    tl.sample(200);
    tl.sample(999);
    expect(seen).toEqual([0, 0.5, 0.5, 1]);
  });

  it('plays on the clock and reports completion', () => {
    const env = fakeRaf();
    const clock = createClock(env);
    let last = -1;
    const onDone = vi.fn();
    play(clock, createTimeline([{ at: 0, duration: 100, apply: (p) => (last = p) }]), {
      reduced: false,
      onDone,
    });
    env.step(0);
    env.step(50);
    expect(last).toBeCloseTo(0.5, 5);
    env.step(100);
    expect(last).toBe(1);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(clock.subscribers).toBe(0);
  });

  it('under reduced motion applies the final state at once without the clock', () => {
    const env = fakeRaf();
    const clock = createClock(env);
    let last = -1;
    const onDone = vi.fn();
    const handle = play(
      clock,
      createTimeline([{ at: 0, duration: 900, apply: (p) => (last = p) }]),
      {
        reduced: true,
        onDone,
      },
    );
    expect(last).toBe(1);
    expect(handle.done).toBe(true);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(clock.subscribers).toBe(0);
  });
});

describe('route geometry (real /route response)', () => {
  const coords = route.coordinates as Coord[];
  const geom = buildRoute(coords);

  it('has a length close to the API distance and connected points', () => {
    expect(coords.length).toBeGreaterThan(5);
    // the API sums edge lengths of the graph; straight segments between nodes are never longer by much
    expect(geom.length).toBeGreaterThan(0.85 * route.distance_m);
    expect(geom.length).toBeLessThan(1.15 * route.distance_m);
    expect(geom.cumulative[0]).toBe(0);
    for (let i = 1; i < geom.cumulative.length; i++)
      expect(geom.cumulative[i]).toBeGreaterThan(geom.cumulative[i - 1] as number);
  });

  it('positionAt hits the ends and stays on the polyline', () => {
    expect(positionAt(geom, 0)).toEqual(coords[0]);
    const end = positionAt(geom, 1);
    expect(end[0]).toBeCloseTo((coords.at(-1) as Coord)[0], 9);
    expect(end[1]).toBeCloseTo((coords.at(-1) as Coord)[1], 9);
    const mid = positionAt(geom, 0.5);
    const fromStart = coords.slice(0, 2).map((c) => haversine(c, mid));
    expect(Math.min(...fromStart)).toBeGreaterThan(0); // not stuck at the first node
    expect(positionAt(geom, -1)).toEqual(coords[0]);
    expect(positionAt(geom, 7)).toEqual(positionAt(geom, 1));
  });

  it('bearing is a compass angle and follows the segment', () => {
    const b = bearingAt(geom, 0.3);
    expect(b).toBeGreaterThanOrEqual(0);
    expect(b).toBeLessThan(360);
    const north = buildRoute([
      [16, 45],
      [16, 45.001],
    ]);
    expect(bearingAt(north, 0.5)).toBeCloseTo(0, 3);
    const east = buildRoute([
      [16, 45],
      [16.001, 45],
    ]);
    expect(bearingAt(east, 0.5)).toBeCloseTo(90, 1);
  });

  it('walkProgress uses the real speed times a constant time-lapse factor', () => {
    const speed = route.speed_mps as number;
    // walking the whole API distance at the persona speed takes distance/speed seconds
    const seconds = geom.length / speed;
    expect(walkProgress(geom, (seconds * 1000) / 30, speed, 30)).toBeCloseTo(1, 6);
    expect(walkProgress(geom, (seconds * 1000) / 60, speed, 30)).toBeCloseTo(0.5, 6);
    expect(walkProgress(geom, 1e9, speed, 30)).toBe(1);
  });
});

describe('flood expressions (real /isochrone response)', () => {
  const features = (isochrone.buckets as { features: { properties: { t: number } }[] }).features;
  const evaluate = (filter: unknown[], t: number): boolean => {
    // tiny evaluator for the three operators we generate
    const ev = (e: unknown): unknown => {
      if (!Array.isArray(e)) return e;
      const [op, ...rest] = e as [string, ...unknown[]];
      if (op === 'get') return t;
      if (op === 'all') return rest.every((r) => ev(r));
      if (op === '<=') return (ev(rest[0]) as number) <= (ev(rest[1]) as number);
      if (op === '>') return (ev(rest[0]) as number) > (ev(rest[1]) as number);
      throw new Error(op);
    };
    return Boolean(ev(filter));
  };

  it('reveals exactly the buckets reached by the clock, never more', () => {
    for (const clock of [0, 2.5, 7.5, 15]) {
      const shown = features.filter((f) => evaluate(floodFilter(clock), f.properties.t));
      expect(shown.every((f) => f.properties.t <= clock + 1e-9)).toBe(true);
      expect(shown.length).toBe(features.filter((f) => f.properties.t <= clock).length);
    }
    expect(features.filter((f) => evaluate(floodFilter(15), f.properties.t)).length).toBe(
      features.length,
    );
  });

  it('the front is a thin slice just behind the clock', () => {
    const front = features.filter((f) => evaluate(frontFilter(10, 0.75), f.properties.t));
    expect(front.length).toBeGreaterThan(0);
    for (const f of front) {
      expect(f.properties.t).toBeLessThanOrEqual(10);
      expect(f.properties.t).toBeGreaterThan(9.25);
    }
  });

  it('floodClock maps screen time to minutes and facilities pop at their minute', () => {
    expect(floodClock(0, 2500, 15)).toBe(0);
    expect(floodClock(1250, 2500, 15)).toBe(7.5);
    expect(floodClock(9999, 2500, 15)).toBe(15);
    expect(isReached(6.8, 6.7)).toBe(false);
    expect(isReached(6.8, 6.8)).toBe(true);
  });
});

describe('planner columns', () => {
  it('blend before -> after linearly and the expression matches', () => {
    expect(columnHeight(100, 40, 0, 2)).toBe(200);
    expect(columnHeight(100, 40, 1, 2)).toBe(80);
    expect(columnHeight(100, 40, 0.5, 2)).toBe(140);
    const e = columnHeightExpression(0.25, 2) as [string, [string, unknown[], unknown[]], number];
    expect(e[0]).toBe('*');
    expect(e[2]).toBe(2);
    expect(e[1][1]).toEqual(['*', ['get', 'unmet_before'], 0.75]);
    expect(e[1][2]).toEqual(['*', ['get', 'unmet_after'], 0.25]);
  });
});

describe('camera', () => {
  const fake = () => ({ flyTo: vi.fn(), easeTo: vi.fn(), jumpTo: vi.fn() });
  const target = presetTarget('orbit', [15.97, 45.81]);

  it('jumps when reduced, eases small moves and flies otherwise with curve 1.42', () => {
    expect(moveKind(true, false)).toBe('jump');
    expect(moveKind(false, true)).toBe('ease');
    expect(moveKind(false, false)).toBe('fly');
    const a = fake();
    moveCamera(a, target, { reduced: true });
    expect(a.jumpTo).toHaveBeenCalledTimes(1);
    expect(a.flyTo).not.toHaveBeenCalled();
    const b = fake();
    moveCamera(b, target, { reduced: false });
    expect(b.flyTo).toHaveBeenCalledWith(
      expect.objectContaining({ curve: 1.42, essential: false, pitch: 60 }),
    );
  });

  it('orbit advances 4 degrees per second', () => {
    expect(orbitBearing(0, 1000)).toBe(4);
    expect(orbitBearing(350, 5000)).toBe(10);
  });
});

describe('scene state and URL sync', () => {
  it('parses and writes ?scena=', () => {
    expect(parseScene('?scena=put')).toBe('put');
    expect(parseScene('?scena=3d&x=1')).toBe('3d');
    expect(parseScene('?scena=nonsense')).toBe('idle');
    expect(parseScene('')).toBe('idle');
    const p = new URLSearchParams('lat=1&lon=2');
    expect(withScene(p, 'doseg').toString()).toBe('lat=1&lon=2&scena=doseg');
    expect(withScene(new URLSearchParams('scena=put&lat=1'), 'idle').toString()).toBe('lat=1');
    expect(p.toString()).toBe('lat=1&lon=2'); // input is not mutated
  });

  it('starts in doseg unless the URL says otherwise and never goes back to idle', () => {
    expect(initialScene('')).toBe('doseg');
    expect(initialScene('?scena=3d')).toBe('3d');
    expect(nextScene('doseg', 'put')).toBe('put');
    expect(nextScene('put', '3d')).toBe('3d');
    expect(nextScene('3d', 'doseg')).toBe('doseg');
    expect(nextScene('put', 'idle')).toBe('put');
  });

  it('3D is unavailable on the raster fallback', () => {
    expect(threeDAvailable(false)).toBe(true);
    expect(threeDAvailable(true)).toBe(false);
  });
});
