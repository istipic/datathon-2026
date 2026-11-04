import { describe, expect, it } from 'vitest';
import { RAMP, breaks, classOf, project, type CountyGeo } from '../components/CountyMap';
import { countdown, formatEur, formatPercent, urgency } from './format';
import { isValidOib, oibStatus } from './oib';

// real OIBs: Sudreg subjects and winners in TED result notices (2026-11-04)
const VALID = ['92803032010', '76860791838', '65605433360', '70869514300', '49733628869', '61817894937'];

describe('OIB checksum', () => {
  it.each(VALID)('accepts %s', (oib) => {
    expect(isValidOib(oib)).toBe(true);
  });

  it.each(VALID)('rejects %s with a wrong check digit', (oib) => {
    const wrong = String((Number(oib[10]) + 1) % 10);
    expect(isValidOib(oib.slice(0, 10) + wrong)).toBe(false);
  });

  it('rejects malformed values', () => {
    for (const v of ['', '123', '9280303201', '928030320100', '9280303201a', '12345678901', '00000000000']) {
      expect(isValidOib(v)).toBe(false);
    }
  });

  it('gives inline status and Croatian messages', () => {
    expect(oibStatus('').status).toBe('empty');
    expect(oibStatus('9280').status).toBe('incomplete');
    expect(oibStatus('9280').message).toContain('Još 7');
    expect(oibStatus('92803032011').status).toBe('invalid');
    expect(oibStatus('92803032011').message).toContain('Kontrolna znamenka');
    expect(oibStatus('92a').status).toBe('invalid');
    expect(oibStatus('92803032010')).toEqual({ status: 'valid', message: 'OIB je ispravan.' });
  });
});

describe('formatting', () => {
  it('formats money, percent and countdown in Croatian', () => {
    expect(formatEur(null)).toBe('nije navedena');
    expect(formatEur(580952)).toMatch(/580\.952/);
    expect(formatPercent(0.4, 0)).toBe('40 %');
    expect(formatPercent(0.1234, 1)).toBe('12,3 %');
    expect(formatPercent(null)).toBe('–');
    expect(countdown(null)).toBe('rok nije naveden');
    expect(countdown(0.4)).toBe('ističe danas');
    expect(countdown(1.2)).toBe('još 1 dan');
    expect(countdown(21.5)).toBe('još 21 dan');
    expect(countdown(12.9)).toBe('još 12 dana');
  });

  it('classifies deadline urgency at the 3 and 15 day edges', () => {
    expect(urgency(15)).toBe('ok');
    expect(urgency(14.9)).toBe('soon');
    expect(urgency(3.1)).toBe('soon');
    expect(urgency(3)).toBe('urgent');
    expect(urgency(null)).toBe('unknown');
  });
});

describe('county map geometry', () => {
  const geo: CountyGeo = {
    features: [
      {
        properties: { nuts3: 'HR050', name: 'Grad Zagreb' },
        geometry: { type: 'Polygon', coordinates: [[[15.8, 45.7], [16.2, 45.7], [16.2, 45.9], [15.8, 45.9], [15.8, 45.7]]] },
      },
      {
        properties: { nuts3: 'HR065', name: 'Zagrebačka županija' },
        geometry: {
          type: 'MultiPolygon',
          coordinates: [[[[16.2, 45.7], [16.6, 45.7], [16.6, 45.9], [16.2, 45.9], [16.2, 45.7]]]],
        },
      },
    ],
  };

  it('projects every feature into a path inside the viewBox', () => {
    const { paths, width, height } = project(geo);
    expect(paths.map((p) => p.nuts3)).toEqual(['HR050', 'HR065']);
    expect(paths.every((p) => p.d.startsWith('M') && p.d.endsWith('Z'))).toBe(true);
    // 0.8 deg of longitude is narrower than 0.2 deg of latitude * 4 because of cos(lat) correction
    expect(width / height).toBeCloseTo((0.8 * Math.cos((45.8 * Math.PI) / 180)) / 0.2, 1);
  });

  it('uses quantile class breaks with zero as its own class', () => {
    const values = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    const t = breaks(values);
    expect(t).toHaveLength(4);
    expect(classOf(0, t)).toBe(-1);
    expect(classOf(1, t)).toBe(0);
    expect(classOf(10, t)).toBe(RAMP.length - 1);
    expect(breaks([0, 0])).toEqual([]);
  });
});
