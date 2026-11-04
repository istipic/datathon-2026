import { readJson, writeJson } from './storage';

export const COUNT_KEY = 'birokratko.bill-count';
export const HIDE_KEY = 'birokratko.bill-hidden';
export const MIN_WAIT_S = 20;
export const MAX_WAIT_S = 40;
export const DRIFT_S = 26; // time the bill needs to cross the screen

export const loadCount = (): number => {
  const n = readJson<number>(COUNT_KEY, 0);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
};

export const saveCount = (n: number): void => writeJson(COUNT_KEY, n);

export const loadHidden = (): boolean => readJson<boolean>(HIDE_KEY, false) === true;

export const saveHidden = (hidden: boolean): void => writeJson(HIDE_KEY, hidden);

/** Wait before the next bill appears: 20-40 s (``rand`` in [0, 1) is injectable for tests). */
export const nextDelayMs = (rand: number = Math.random()): number =>
  Math.round((MIN_WAIT_S + (MAX_WAIT_S - MIN_WAIT_S) * rand) * 1000);

/** Vertical position of the next bill as a share of the viewport height (kept off the navigation bar). */
export const nextLane = (rand: number = Math.random()): number => 0.18 + 0.6 * rand;

/** "Ulovljeno: 3 €". */
export const counterLabel = (n: number): string => `Ulovljeno: ${n} €`;

/** Routes on which the bill is never shown (subscription confirm / unsubscribe / settings). */
export const isQuietRoute = (pathname: string): boolean => pathname.startsWith('/pretplata');

export interface BillMode {
  /** The bill drifts across the screen (false: it sits in a corner, reduced motion). */
  drifting: boolean;
}

export const billMode = (reducedMotion: boolean): BillMode => ({ drifting: !reducedMotion });
