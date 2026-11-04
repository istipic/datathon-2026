import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  COUNT_KEY,
  DRIFT_S,
  HIDE_KEY,
  billMode,
  counterLabel,
  isQuietRoute,
  nextDelayMs,
  nextLane,
} from '../lib/banknote';
import { useStored } from '../lib/storage';
import { useAlertDialog } from './AlertDialog';

/** True when the visitor asked the OS for reduced motion (updates live). */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduced;
}

/** The little euro bill (SVG, tokens of the design system). */
function BillSvg() {
  return (
    <svg width="72" height="36" viewBox="0 0 72 36" aria-hidden="true" focusable="false">
      <rect
        x="1"
        y="1"
        width="70"
        height="34"
        rx="4"
        fill="#ffe17c"
        stroke="#000"
        strokeWidth="2"
      />
      <rect
        x="6"
        y="6"
        width="60"
        height="24"
        rx="2"
        fill="none"
        stroke="#000"
        strokeWidth="1.5"
        strokeDasharray="3 2"
      />
      <circle cx="36" cy="18" r="9" fill="#b7c6c2" stroke="#000" strokeWidth="2" />
      <text
        x="36"
        y="23"
        textAnchor="middle"
        fontSize="13"
        fontWeight="800"
        fontFamily="Arial, sans-serif"
        fill="#000"
      >
        €
      </text>
      <circle cx="12" cy="18" r="2.5" fill="#000" />
      <circle cx="60" cy="18" r="2.5" fill="#000" />
    </svg>
  );
}

/** Footer pill with the counter and the "hide the bill" switch (both remembered in localStorage). */
export function BillCounter() {
  const [count] = useStored<number>(COUNT_KEY, 0);
  const [hidden, setHidden] = useStored<boolean>(HIDE_KEY, false);
  return (
    <div className="nb-counter">
      <span className="nb-pill" role="status" aria-live="polite" data-testid="bill-counter">
        {counterLabel(count)}
      </span>
      <button
        type="button"
        className="nb-btn nb-btn--light nb-btn--sm"
        aria-pressed={hidden}
        onClick={() => setHidden(!hidden)}
      >
        {hidden ? 'Prikaži novčanicu' : 'Sakrij novčanicu'}
      </button>
    </div>
  );
}

interface Pop {
  id: number;
  x: number;
  y: number;
}

/**
 * A euro bill that drifts across the screen every 20-40 s. Click, Enter or Space catches it (+1 EUR, a short
 * flip and a "+1 €" pop). With reduced motion it rests in a corner. Never shown on subscription pages, while
 * a dialog is open, in print, or after "Sakrij novčanicu".
 */
export function Banknote() {
  const { pathname } = useLocation();
  const { isOpen } = useAlertDialog();
  const reduced = useReducedMotion();
  const mode = billMode(reduced);
  const [, setCount] = useStored<number>(COUNT_KEY, 0);
  const [hidden] = useStored<boolean>(HIDE_KEY, false);
  const [present, setPresent] = useState(false);
  const [caught, setCaught] = useState(false);
  const [lane, setLane] = useState(0.4);
  const [pops, setPops] = useState<Pop[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const button = useRef<HTMLButtonElement | null>(null);

  const quiet = isQuietRoute(pathname) || hidden;

  const schedule = useCallback((ms: number) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setLane(nextLane());
      setCaught(false);
      setPresent(true);
    }, ms);
  }, []);

  useEffect(() => {
    if (quiet) {
      if (timer.current) clearTimeout(timer.current);
      setPresent(false);
      return;
    }
    if (!mode.drifting) {
      setPresent(true); // it rests in the corner
      return;
    }
    if (!present) schedule(present ? 0 : 4000);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
    // present is intentionally not a dependency: scheduling happens when the bill leaves
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quiet, mode.drifting, schedule]);

  if (quiet || isOpen || !present) return null;

  const leave = () => {
    setPresent(false);
    setCaught(false);
    if (mode.drifting) schedule(nextDelayMs());
  };

  const catchBill = () => {
    setCount((n) => (Number.isFinite(n) ? n : 0) + 1);
    if (!mode.drifting) return; // reduced motion: only the counter changes
    const rect = button.current?.getBoundingClientRect();
    const id = Date.now();
    setPops((p) => [...p, { id, x: (rect?.left ?? 0) + 12, y: (rect?.top ?? 0) - 8 }]);
    setCaught(true);
    setTimeout(() => setPops((p) => p.filter((x) => x.id !== id)), 650);
    setTimeout(leave, 600);
  };

  return (
    <>
      <button
        ref={button}
        type="button"
        aria-label="Uhvati novčanicu"
        className={`nb-bill ${mode.drifting ? 'nb-bill--drift' : 'nb-bill--still'} ${caught ? 'nb-bill--caught' : ''}`}
        style={
          mode.drifting
            ? ({
                top: `${Math.round(lane * 100)}vh`,
                '--drift-s': `${DRIFT_S}s`,
                '--bob': `${Math.round(24 + lane * 40)}px`,
              } as React.CSSProperties)
            : undefined
        }
        onClick={catchBill}
        onAnimationEnd={(e) => {
          if (mode.drifting && e.animationName === 'nb-drift') leave();
        }}
      >
        <BillSvg />
      </button>
      {pops.map((p) => (
        <span key={p.id} className="nb-pop" style={{ left: p.x, top: p.y }} aria-hidden="true">
          +1 €
        </span>
      ))}
    </>
  );
}
