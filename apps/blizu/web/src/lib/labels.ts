import type { CategoryId, Grade, PersonaId } from './types';

export const PERSONAS: { id: PersonaId; label: string; hint: string }[] = [
  { id: 'opce', label: 'Opće', hint: 'prosječna brzina hoda 1,33 m/s' },
  { id: 'starija', label: 'Starija osoba', hint: 'sporiji hod, 0,90 m/s' },
  { id: 'roditelj', label: 'Roditelj s djetetom', hint: 'hod 1,10 m/s' },
  { id: 'kolica', label: 'Invalidska kolica', hint: 'bez stepenica, 0,90 m/s' },
];

export const PERSONA_LABEL: Record<PersonaId, string> = Object.fromEntries(
  PERSONAS.map((p) => [p.id, p.label]),
) as Record<PersonaId, string>;

export const GRADE_COLOR: Record<Grade, string> = {
  A: '#1A7F37',
  B: '#4D9221',
  C: '#9A7D0A',
  D: '#D35400',
  E: '#B03A2E',
};

export const TIER_LABEL: Record<string, string> = {
  official: 'službeni izvor',
  eu_official: 'službeni izvor (EU)',
  community: 'zajednica (OpenStreetMap)',
  derived: 'izvedeno',
};

export const CATEGORY_SHORT: Record<CategoryId, string> = {
  lijecnik: 'Liječnik',
  ljekarna: 'Ljekarna',
  vrtic: 'Vrtić',
  skola: 'Škola',
  knjiznica: 'Knjižnica',
  posta: 'Pošta',
  prijevoz: 'Prijevoz',
  park: 'Park',
  namirnice: 'Trgovina',
};

export function isPersona(value: string | null): value is PersonaId {
  return value === 'opce' || value === 'starija' || value === 'roditelj' || value === 'kolica';
}

/** "12 min" / "1 min" with a Croatian decimal comma; null -> "–". */
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '–';
  const rounded = Math.round(minutes);
  return `${rounded} min`;
}

/** Share 0..1 as "63 %" (Croatian: space before the percent sign). */
export function formatPercent(share: number | null | undefined): string {
  if (share === null || share === undefined) return '–';
  return `${Math.round(share * 100)} %`;
}

export function formatInt(n: number): string {
  return new Intl.NumberFormat('hr-HR').format(Math.round(n));
}
