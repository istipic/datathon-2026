import { useCallback, useEffect, useState } from 'react';
import type { MatchItem } from './types';

/** localStorage that never throws (private windows, blocked storage, quota). */
export function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: the value lives for this visit only */
  }
}

const EVENT = 'birokratko-storage';

/** A localStorage-backed state that stays in sync between components and browser tabs. */
export function useStored<T>(key: string, fallback: T): [T, (next: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => readJson(key, fallback));
  useEffect(() => {
    const sync = () => setValue(readJson(key, fallback));
    window.addEventListener(EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener('storage', sync);
    };
    // fallback is a constant default of the caller
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      const resolved =
        typeof next === 'function' ? (next as (p: T) => T)(readJson(key, fallback)) : next;
      writeJson(key, resolved);
      setValue(resolved);
      window.dispatchEvent(new Event(EVENT));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  );
  return [value, set];
}

// ------------------------------------------------------------------------------ saved tenders

export const SAVED_KEY = 'birokratko.saved';

/** What is kept of a saved tender (enough to list it without the API). */
export interface SavedTender {
  pub_no: string;
  title: string | null;
  buyer: string | null;
  county: string | null;
  deadline: string | null;
  value_eur: number | null;
  fit: number;
  url_html: string | null;
  saved_at: string;
}

export const toSaved = (item: MatchItem, now = new Date()): SavedTender => ({
  pub_no: item.pub_no,
  title: item.title,
  buyer: item.buyer,
  county: item.county,
  deadline: item.deadline,
  value_eur: item.value_eur,
  fit: item.fit,
  url_html: item.url_html,
  saved_at: now.toISOString(),
});

/** Add or remove ``item`` from a saved list (pure; the caller persists the result). */
export function toggleSaved(list: SavedTender[], item: MatchItem, now = new Date()): SavedTender[] {
  return list.some((s) => s.pub_no === item.pub_no)
    ? list.filter((s) => s.pub_no !== item.pub_no)
    : [toSaved(item, now), ...list];
}

// ------------------------------------------------------------------------------ "Ne zanima me"

export const HIDDEN_KEY = 'birokratko.hidden';
export const DISLIKED_KEY = 'birokratko.disliked-groups';
export const MAX_HIDDEN = 300; // the API accepts at most this many `hide` values
export const MAX_DISLIKED = 60;

/** Append without duplicates, keeping the newest entries when the API limit is reached. */
export function addCapped(list: string[], value: string, max: number): string[] {
  const without = list.filter((v) => v !== value);
  return [...without, value].slice(-max);
}
