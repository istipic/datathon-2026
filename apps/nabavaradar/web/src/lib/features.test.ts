import { afterEach, describe, expect, it } from 'vitest';
import grouped from '../__fixtures__/2026-11-05_match_koncar_grouped.json';
import { arrange } from '../pages/CompanyPage';
import {
  COUNT_KEY,
  HIDE_KEY,
  billMode,
  counterLabel,
  isQuietRoute,
  loadCount,
  loadHidden,
  nextDelayMs,
  nextLane,
  saveCount,
  saveHidden,
} from './banknote';
import { CSV_HEADER, buildIcs, csvField, icsEscape, icsFold, icsStamp, toCsv } from './export';
import { addCapped, readJson, toggleSaved, writeJson } from './storage';
import type { MatchItem } from './types';

// The fixture is a REAL /api/v1/match response (KONČAR, recorded 2026-11-05 from the running API).
const items = grouped as unknown as MatchItem[];

afterEach(() => window.localStorage.clear());

describe('calendar export (.ics)', () => {
  const item = items[0] as MatchItem;
  it('writes a valid VEVENT for the deadline with a reminder one day before', () => {
    const ics = buildIcs(item, new Date('2026-11-05T10:00:00Z')) as string;
    expect(ics.startsWith('BEGIN:VCALENDAR\r\n')).toBe(true);
    expect(ics.endsWith('END:VCALENDAR\r\n')).toBe(true);
    expect(ics).toContain(`UID:${item.pub_no}@birokratko`);
    expect(ics).toContain('DTSTAMP:20261105T100000Z');
    expect(ics).toContain('DTEND:20261120T080000Z'); // the deadline of the recorded notice
    expect(ics).toContain('DTSTART:20261120T073000Z');
    expect(ics).toContain('TRIGGER:-P1D');
    expect(ics).toContain('SUMMARY:Rok za ponude');
    expect(ics).toContain(`URL:${item.url_html}`);
  });
  it('returns null without a usable deadline', () => {
    expect(buildIcs({ ...item, deadline: null })).toBeNull();
    expect(buildIcs({ ...item, deadline: 'nonsense' })).toBeNull();
  });
  it('escapes text, folds long lines at 75 octets and stamps UTC', () => {
    expect(icsEscape('a,b;c\\d\ne')).toBe('a\\,b\\;c\\\\d\\ne');
    expect(icsStamp(new Date('2026-01-02T03:04:05Z'))).toBe('20260102T030405Z');
    const folded = icsFold(`SUMMARY:${'č'.repeat(80)}`);
    for (const line of folded.split('\r\n')) {
      expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75);
    }
    expect(folded.replace(/\r\n /g, '')).toBe(`SUMMARY:${'č'.repeat(80)}`);
  });
});

describe('CSV export', () => {
  it('starts with a BOM so Excel shows č ć š ž đ, uses ; and CRLF', () => {
    const csv = toCsv(items);
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    const lines = csv.slice(1).split('\r\n');
    expect(lines[0]).toBe(CSV_HEADER.join(';'));
    expect(lines.length).toBe(items.length + 2); // header + rows + trailing newline
    expect(lines[1]).toContain(`;${(items[0] as MatchItem).pub_no};`);
  });
  it('quotes separators and quotes, and neutralises spreadsheet formulas', () => {
    expect(csvField('a;b')).toBe('"a;b"');
    expect(csvField('say "hi"')).toBe('"say ""hi"""');
    expect(csvField('=SUM(A1)')).toBe("'=SUM(A1)");
    expect(csvField(-5)).toBe('-5'); // numbers are not formulas
    expect(csvField(null)).toBe('');
  });
});

describe('saved tenders and hidden notices (browser only)', () => {
  const item = items[0] as MatchItem;
  it('toggles a saved tender on and off', () => {
    const once = toggleSaved([], item, new Date('2026-11-05T00:00:00Z'));
    expect(once).toHaveLength(1);
    expect(once[0]?.pub_no).toBe(item.pub_no);
    expect(once[0]?.saved_at).toBe('2026-11-05T00:00:00.000Z');
    expect(toggleSaved(once, item)).toEqual([]);
  });
  it('keeps the newest entries when the API limit is reached and drops duplicates', () => {
    expect(addCapped(['a', 'b'], 'a', 5)).toEqual(['b', 'a']);
    expect(addCapped(['a', 'b', 'c'], 'd', 3)).toEqual(['b', 'c', 'd']);
  });
  it('never throws when storage holds garbage', () => {
    window.localStorage.setItem('k', '{not json');
    expect(readJson('k', 7)).toBe(7);
    writeJson('k', { ok: true });
    expect(readJson('k', null)).toEqual({ ok: true });
  });
});

describe('banknote logic', () => {
  it('waits 20-40 s between bills', () => {
    expect(nextDelayMs(0)).toBe(20_000);
    expect(nextDelayMs(0.5)).toBe(30_000);
    expect(nextDelayMs(0.999)).toBeLessThanOrEqual(40_000);
    for (let i = 0; i < 50; i++) {
      const ms = nextDelayMs();
      expect(ms).toBeGreaterThanOrEqual(20_000);
      expect(ms).toBeLessThanOrEqual(40_000);
    }
  });
  it('keeps the bill off the navigation bar', () => {
    expect(nextLane(0)).toBeGreaterThanOrEqual(0.18);
    expect(nextLane(0.999)).toBeLessThanOrEqual(0.8);
  });
  it('persists the counter and the hide switch, and survives broken values', () => {
    expect(loadCount()).toBe(0);
    saveCount(3);
    expect(loadCount()).toBe(3);
    expect(counterLabel(3)).toBe('Ulovljeno: 3 €');
    window.localStorage.setItem(COUNT_KEY, '"abc"');
    expect(loadCount()).toBe(0);
    window.localStorage.setItem(COUNT_KEY, '-4');
    expect(loadCount()).toBe(0);
    expect(loadHidden()).toBe(false);
    saveHidden(true);
    expect(loadHidden()).toBe(true);
    window.localStorage.setItem(HIDE_KEY, '"yes"');
    expect(loadHidden()).toBe(false);
  });
  it('does not drift under reduced motion and stays away from subscription pages', () => {
    expect(billMode(true).drifting).toBe(false);
    expect(billMode(false).drifting).toBe(true);
    expect(isQuietRoute('/pretplata/odjava')).toBe(true);
    expect(isQuietRoute('/pretplata/postavke')).toBe(true);
    expect(isQuietRoute('/tvrtka/45050126417')).toBe(false);
  });
});

describe('result list: sort and search', () => {
  it('sorts by deadline and by value, and keeps the API order for fit', () => {
    expect(arrange(items, 'fit', '')).toEqual(items);
    const byDeadline = arrange(items, 'deadline', '');
    const days = byDeadline.map((i) => i.days_left ?? Infinity);
    expect(days).toEqual([...days].sort((a, b) => a - b));
    const byValue = arrange(items, 'value', '').map((i) => i.value_eur ?? -1);
    expect(byValue).toEqual([...byValue].sort((a, b) => b - a));
  });
  it('searches title, buyer and county case-insensitively', () => {
    const first = items[0] as MatchItem;
    const word = (first.buyer ?? '').split(' ')[0] as string;
    const hits = arrange(items, 'fit', word.toLowerCase());
    expect(hits.length).toBeGreaterThan(0);
    expect(
      hits.every((i) =>
        `${i.title} ${i.buyer} ${i.county}`.toLowerCase().includes(word.toLowerCase()),
      ),
    ).toBe(true);
    expect(arrange(items, 'fit', 'zzzzzz-nothing')).toEqual([]);
  });
});

describe('real match fixture carries the new signals', () => {
  it('has groups of publications of one procedure', () => {
    expect(items.every((i) => i.group && i.group.size >= 1)).toBe(true);
    const grouped = items.find((i) => (i.group?.size ?? 1) > 1);
    expect(grouped).toBeTruthy();
    expect(grouped?.group?.others.length).toBe((grouped?.group?.size ?? 1) - 1);
    expect(items.every((i) => i.signals && typeof i.signals.main_activity === 'boolean')).toBe(
      true,
    );
  });
});
