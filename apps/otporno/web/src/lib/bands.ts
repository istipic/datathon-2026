import type { Band, Confidence } from './types';

export const BANDS: Band[] = ['niska', 'umjerena', 'visoka', 'vrlo visoka'];

/** 0-3 position of a band (used for ring segments); -1 when unknown. */
export const bandIndex = (band: Band | null): number => (band ? BANDS.indexOf(band) : -1);

export const BAND_LABEL: Record<Band, string> = {
  niska: 'Niska',
  umjerena: 'Umjerena',
  visoka: 'Visoka',
  'vrlo visoka': 'Vrlo visoka',
};

/** Heat sequential scale (light to dark orange/red); every use is paired with the band text. */
export const HEAT_FILL: Record<Band, string> = {
  niska: '#FDE9C9',
  umjerena: '#F9B572',
  visoka: '#E8661F',
  'vrlo visoka': '#9A2A0B',
};

/** Choropleth classes of the priority map (class -1 = no priority). */
export const PRIORITY_FILL = ['#E7E1D6', '#FCD9A8', '#F6A55B', '#DD6A1E', '#8F2D0C'];
export const PRIORITY_LABEL = ['Bez prioriteta', 'Niži', 'Srednji', 'Visok', 'Najviši'];

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  visoka: 'Visoka pouzdanost',
  srednja: 'Srednja pouzdanost',
  niska: 'Niska pouzdanost',
};

export function priorityColor(cls: number): string {
  return PRIORITY_FILL[Math.max(0, cls + 1)] ?? PRIORITY_FILL[0]!;
}

export const WMS_SCENARIOS = [
  { key: 'high', label: 'Velika vjerojatnost', hint: 'česta pojava' },
  { key: 'medium', label: 'Srednja vjerojatnost', hint: 'rijetka pojava' },
  { key: 'low', label: 'Mala vjerojatnost', hint: 'iznimna pojava' },
] as const;

/** XYZ tile URL template of one HV hazard layer (WMS 1.3.0, EPSG:3857; MapLibre fills {bbox-epsg-3857}). */
export function wmsTileUrl(base: string, layer: string): string {
  const params = new URLSearchParams({
    SERVICE: 'WMS',
    VERSION: '1.3.0',
    REQUEST: 'GetMap',
    LAYERS: layer,
    STYLES: '',
    FORMAT: 'image/png',
    TRANSPARENT: 'true',
    CRS: 'EPSG:3857',
    WIDTH: '256',
    HEIGHT: '256',
  });
  return `${base}?${params.toString()}&BBOX={bbox-epsg-3857}`;
}

export function legendUrl(base: string, layer: string): string {
  const params = new URLSearchParams({
    SERVICE: 'WMS',
    VERSION: '1.3.0',
    REQUEST: 'GetLegendGraphic',
    FORMAT: 'image/png',
    LAYER: layer,
  });
  return `${base}?${params.toString()}`;
}
