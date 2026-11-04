import { pluralDays } from '@dt/ui';

const eur = new Intl.NumberFormat('hr-HR', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
});
const num1 = new Intl.NumberFormat('hr-HR', { maximumFractionDigits: 1 });
const dateFmt = new Intl.DateTimeFormat('hr-HR', {
  day: 'numeric',
  month: 'numeric',
  year: 'numeric',
  timeZone: 'Europe/Zagreb',
});
const dateTimeFmt = new Intl.DateTimeFormat('hr-HR', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Europe/Zagreb',
});

export const formatEur = (value: number | null | undefined) =>
  value === null || value === undefined ? 'nije navedena' : eur.format(value);

export const formatNumber = (value: number | null | undefined) =>
  value === null || value === undefined ? '–' : num1.format(value);

export const formatPercent = (value: number | null | undefined, digits = 0) =>
  value === null || value === undefined ? '–' : `${(value * 100).toFixed(digits).replace('.', ',')} %`;

export function formatDate(value: string | null | undefined): string {
  if (!value) return '–';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '–' : dateFmt.format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '–';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '–' : dateTimeFmt.format(date);
}

/** "još 12 dana", "još 1 dan", "ističe danas". */
export function countdown(daysLeft: number | null | undefined): string {
  if (daysLeft === null || daysLeft === undefined) return 'rok nije naveden';
  if (daysLeft < 1) return 'ističe danas';
  const whole = Math.floor(daysLeft);
  return `još ${whole} ${pluralDays(whole)}`;
}

export type Urgency = 'ok' | 'soon' | 'urgent' | 'unknown';

/** Deadline urgency: matches the T component (15 / 3 days). */
export function urgency(daysLeft: number | null | undefined): Urgency {
  if (daysLeft === null || daysLeft === undefined) return 'unknown';
  if (daysLeft <= 3) return 'urgent';
  if (daysLeft < 15) return 'soon';
  return 'ok';
}

/** Croatian label for the fit components. */
export const COMPONENT_LABELS = {
  S: 'Sličnost opisa',
  C: 'CPV područje',
  G: 'Lokacija',
  T: 'Preostalo vrijeme',
} as const;
