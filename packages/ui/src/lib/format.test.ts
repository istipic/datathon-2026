import { formatDateTime, formatDays, pluralDays, toIso } from './format';

describe('pluralDays', () => {
  it.each([
    [0, 'dana'],
    [1, 'dan'],
    [2, 'dana'],
    [4, 'dana'],
    [5, 'dana'],
    [11, 'dana'],
    [21, 'dan'],
    [101, 'dan'],
    [111, 'dana'],
    [365, 'dana'],
  ])('%i → %s', (n, word) => {
    expect(pluralDays(n)).toBe(word);
  });
});

describe('formatDays', () => {
  it('joins number and word', () => {
    expect(formatDays(1)).toBe('1 dan');
    expect(formatDays(12)).toBe('12 dana');
  });
});

describe('formatDateTime', () => {
  it('formats in Croatian, Europe/Zagreb time', () => {
    // 2026-11-03T18:31:50Z is 19:31 in Zagreb (CET, UTC+1)
    const out = formatDateTime('2026-11-03T18:31:50Z');
    expect(out).toContain('2026');
    expect(out).toContain('19:31');
  });

  it('accepts Date objects', () => {
    expect(formatDateTime(new Date('2026-01-15T10:00:00Z'))).toContain('11:00');
  });

  it.each([null, undefined, '', 'not a date'])('returns null for %s', (value) => {
    expect(formatDateTime(value)).toBeNull();
    expect(toIso(value)).toBeUndefined();
  });

  it('toIso normalises to ISO 8601 UTC', () => {
    expect(toIso('2026-11-03T19:31:50+01:00')).toBe('2026-11-03T18:31:50.000Z');
  });
});
