import { describe, expect, it } from 'vitest';
import { rebalance } from '../components/WeightSliders';
import { BANDS, bandIndex, legendUrl, priorityColor, PRIORITY_FILL, wmsTileUrl } from './bands';
import { fmtDec, fmtInt, fmtPct, pluralDays } from './format';

describe('format', () => {
  it('uses Croatian separators', () => {
    expect(fmtInt(49669)).toBe('49.669');
    expect(fmtDec(30.64)).toBe('30,6');
    expect(fmtInt(null)).toBe('–');
    expect(fmtPct(0.424)).toBe('42 %');
  });
  it('pluralises "dan"', () => {
    expect(pluralDays(1)).toBe('dan');
    expect(pluralDays(21)).toBe('dan');
    expect(pluralDays(11)).toBe('dana');
    expect(pluralDays(5)).toBe('dana');
    expect(pluralDays(30.6)).toBe('dana');
  });
});

describe('bands', () => {
  it('orders the four bands', () => {
    expect(BANDS).toEqual(['niska', 'umjerena', 'visoka', 'vrlo visoka']);
    expect(bandIndex('visoka')).toBe(2);
    expect(bandIndex(null)).toBe(-1);
  });
  it('maps priority classes to colours (class -1 = no priority)', () => {
    expect(priorityColor(-1)).toBe(PRIORITY_FILL[0]);
    expect(priorityColor(3)).toBe(PRIORITY_FILL[4]);
  });
  it('builds a WMS tile template with the MapLibre bbox placeholder', () => {
    const url = wmsTileUrl(
      'https://servisi.voda.hr/wms',
      'poplave_opasnosti_2019:hr.fd.opasnost-od-poplave-velika-vjerojatnost_2019',
    );
    expect(url).toContain('REQUEST=GetMap');
    expect(url).toContain('CRS=EPSG%3A3857');
    expect(url).toContain('TRANSPARENT=true');
    expect(url.endsWith('&BBOX={bbox-epsg-3857}')).toBe(true);
    expect(legendUrl('https://servisi.voda.hr/wms', 'x')).toContain('REQUEST=GetLegendGraphic');
  });
});

describe('rebalance (weights stay at 100 %)', () => {
  const start = { flood: 0.5, heat: 0.35, fire: 0.15 };
  it('keeps the sum at 1 and the ratio of the others', () => {
    const w = rebalance(start, 'heat', 0.7);
    expect(w.heat).toBe(0.7);
    expect(Math.abs(w.flood + w.heat + w.fire - 1)).toBeLessThan(1e-9);
    expect(w.flood / w.fire).toBeCloseTo(0.5 / 0.15, 0);
  });
  it('handles the extremes', () => {
    const one = rebalance(start, 'flood', 1);
    expect(one).toEqual({ flood: 1, heat: 0, fire: 0 });
    const zero = rebalance({ flood: 1, heat: 0, fire: 0 }, 'flood', 0);
    expect(Math.abs(zero.flood + zero.heat + zero.fire - 1)).toBeLessThan(1e-9);
  });
});
