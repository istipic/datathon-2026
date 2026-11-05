import need from '../__fixtures__/2026-11-03_need_vrtic_roditelj_summary.json';
import problem from '../__fixtures__/2026-11-03_problem_422.json';
import { ApiError, api } from './api';
import {
  countText,
  formatInt,
  formatMinutes,
  formatPercent,
  GRADE_COLOR,
  isPersona,
  minutesWord,
} from './labels';
import { legendClasses, NEED_COLORS } from './legend';

// All fixtures are REAL API responses recorded on 2026-11-03.

afterEach(() => vi.unstubAllGlobals());

describe('labels', () => {
  it('formats minutes, percent and integers for Croatian', () => {
    expect(formatMinutes(null)).toBe('–');
    expect(formatMinutes(0.4)).toBe('0 min');
    expect(formatMinutes(12.6)).toBe('13 min');
    expect(formatPercent(0.6787)).toBe('68 %');
    expect(formatPercent(null)).toBe('–');
    expect(formatInt(115944)).toMatch(/^115\D?944$/); // hr-HR groups thousands with a dot
  });

  it('validates persona ids', () => {
    expect(isPersona('kolica')).toBe(true);
    expect(isPersona('robot')).toBe(false);
    expect(isPersona(null)).toBe(false);
  });

  it('grade colours give white text at least 3:1 (large text, WCAG AA)', () => {
    const lum = (hex: string) => {
      const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
      const f = (v: number) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
      return 0.2126 * f(r!) + 0.7152 * f(g!) + 0.0722 * f(b!);
    };
    for (const [grade, color] of Object.entries(GRADE_COLOR)) {
      expect(1.05 / (lum(color) + 0.05), grade).toBeGreaterThanOrEqual(3);
    }
    expect(Object.keys(GRADE_COLOR)).toEqual(['A', 'B', 'C', 'D', 'E']);
  });
});

describe('legendClasses (real unmet-need quantiles)', () => {
  it('turns the 4 quantile breaks into 5 classes with numeric bounds', () => {
    const classes = legendClasses(need.summary.breaks, Math.ceil(need.max_unmet));
    expect(classes).toHaveLength(5);
    expect(classes.map((c) => c.color)).toEqual(NEED_COLORS);
    expect(classes[0]).toMatchObject({ from: 0, to: 8 });
    expect(classes[1]).toMatchObject({ from: 8, to: 19 });
    expect(classes[4]!.from).toBeGreaterThan(classes[3]!.from);
    expect(classes[4]!.to).toBe(Math.ceil(need.max_unmet));
    for (let i = 1; i < classes.length; i++) expect(classes[i]!.from).toBe(classes[i - 1]!.to);
  });

  it('collapses duplicate breaks and handles an empty list', () => {
    expect(legendClasses([5, 5, 5, 5], 20)).toHaveLength(2);
    const single = legendClasses([], 12);
    expect(single).toHaveLength(1);
    expect(single[0]).toMatchObject({ from: 0, to: 12 });
    expect(legendClasses([], 0)[0]!.to).toBeNull();
  });
});

describe('api client', () => {
  it('maps a problem+json response to ApiError with the server detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ ...problem, detail: 'Adresa nije unutar Grada Zagreba.' }),
            { status: 422 },
          ),
      ),
    );
    const error = await api.access(48.85, 2.35, 'opce').catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(422);
    expect(error.message).toBe('Adresa nije unutar Grada Zagreba.');
  });

  it('falls back to the title and to a status message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ title: 'Not Found' }), { status: 404 })),
    );
    expect((await api.scoring().catch((e) => e)).message).toBe('Not Found');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('<html>', { status: 502 })),
    );
    expect((await api.scoring().catch((e) => e)).message).toContain('502');
  });

  it('reports an unreachable server in Croatian with status 0', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Promise.reject(new TypeError('network'))),
    );
    const error = await api.scoring().catch((e) => e);
    expect(error.status).toBe(0);
    expect(error.message).toContain('poslužitelja');
  });

  it('builds query strings and posts JSON', async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push([url, init]);
        return new Response('{}', { status: 200 });
      }),
    );
    await api.access(45.81277, 15.97659, 'starija');
    await api.optimise('vrtic', 'roditelj', 3);
    expect(calls[0]![0]).toBe('/api/v1/access?lat=45.81277&lon=15.97659&persona=starija');
    expect(calls[1]![0]).toBe('/api/v1/plan/optimise');
    expect(JSON.parse(String(calls[1]![1]!.body))).toEqual({
      category: 'vrtic',
      persona: 'roditelj',
      k: 3,
    });
  });
});

describe('Croatian count and minute words', () => {
  it('declines minutes and counts', () => {
    expect(minutesWord(1)).toBe('1 minuta');
    expect(minutesWord(3)).toBe('3 minute');
    expect(minutesWord(10)).toBe('10 minuta');
    expect(minutesWord(12)).toBe('12 minuta');
    expect(minutesWord(22)).toBe('22 minute');
    expect(countText('ljekarna', 1)).toBe('1 ljekarna');
    expect(countText('ljekarna', 2)).toBe('2 ljekarne');
    expect(countText('ljekarna', 5)).toBe('5 ljekarni');
    expect(countText('skola', 1)).toBe('1 škola');
    expect(countText('prijevoz', 37)).toBe('37 postaja');
    expect(countText('park', 11)).toBe('11 parkova');
  });
});
