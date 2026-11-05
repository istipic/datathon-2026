import { useEffect, useRef } from 'react';
import { clock, prefersReducedMotion } from '../lib/anim/clock';
import { easeOutCubic } from '../lib/anim/easing';
import { createTimeline, play, throttleApply } from '../lib/anim/timeline';
import { formatInt } from '../lib/labels';

interface Props {
  /** The real value (e.g. `total_newly_covered` from the API); the animation always ends exactly here. */
  value: number;
  ms?: number;
  prefix?: string;
  suffix?: string;
  testId?: string;
}

/**
 * Counts from 0 to `value`. The text is written to the DOM node directly (no React state per frame);
 * the rendered text is the final value, so with reduced motion or before the effect runs it is already right.
 */
export function CountUp({ value, ms = 900, prefix = '', suffix = '', testId }: Props) {
  const ref = useRef<HTMLSpanElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const write = (n: number) => {
      el.textContent = `${prefix}${formatInt(n)}${suffix}`;
    };
    const handle = play(
      clock,
      createTimeline([
        {
          at: 0,
          duration: ms,
          ease: easeOutCubic,
          apply: throttleApply((p) => write(p >= 1 ? value : value * p)),
        },
      ]),
      { reduced: prefersReducedMotion(), onDone: () => write(value) },
    );
    return () => {
      handle.cancel();
      write(value);
    };
  }, [value, ms, prefix, suffix]);
  return (
    <span ref={ref} className="dt-num" data-testid={testId}>
      {prefix}
      {formatInt(value)}
      {suffix}
    </span>
  );
}
