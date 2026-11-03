import { formatDays } from '../lib/format';

export interface FreshnessChipProps {
  /** Age of the data in days; null/undefined when unknown. */
  days: number | null | undefined;
}

type Level = 'success' | 'warning' | 'danger' | 'neutral';

/** green <= 30 days, amber <= 365, red > 365. */
export function freshnessLevel(days: number | null | undefined): Level {
  if (days === null || days === undefined || Number.isNaN(days)) return 'neutral';
  if (days <= 30) return 'success';
  if (days <= 365) return 'warning';
  return 'danger';
}

const LABEL: Record<Level, string> = {
  success: 'ažurno',
  warning: 'starije',
  danger: 'zastarjelo',
  neutral: 'nepoznato',
};
// Different glyph shapes so the state is not carried by colour alone.
const GLYPH: Record<Level, string> = { success: '✓', warning: '!', danger: '✕', neutral: '?' };

/** Chip showing how old the data is. Colour is supplementary: text and glyph always present. */
export function FreshnessChip({ days }: FreshnessChipProps) {
  const level = freshnessLevel(days);
  const known = days !== null && days !== undefined && !Number.isNaN(days);
  return (
    <span className={`dt-chip dt-chip--${level}`} data-level={level}>
      <span aria-hidden="true">{GLYPH[level]}</span>
      <span>
        {known
          ? `Starost podataka: ${formatDays(days as number)} (${LABEL[level]})`
          : 'Starost podataka nije poznata'}
      </span>
    </span>
  );
}
