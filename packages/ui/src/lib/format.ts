/** Croatian plural of "dan" (day): 1, 21, 31 → "dan"; everything else → "dana". */
export function pluralDays(n: number): string {
  const abs = Math.abs(Math.trunc(n));
  return abs % 10 === 1 && abs % 100 !== 11 ? 'dan' : 'dana';
}

/** "12 dana", "1 dan", "21 dan". */
export function formatDays(n: number): string {
  return `${n} ${pluralDays(n)}`;
}

const dateTimeFormat = new Intl.DateTimeFormat('hr-HR', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Europe/Zagreb',
});

/** Format a timestamp for display in Croatian (Europe/Zagreb). Returns null if invalid/missing. */
export function formatDateTime(value: string | Date | null | undefined): string | null {
  if (value === null || value === undefined || value === '') return null;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return dateTimeFormat.format(date);
}

/** ISO string for the <time dateTime> attribute, or undefined if invalid/missing. */
export function toIso(value: string | Date | null | undefined): string | undefined {
  if (value === null || value === undefined || value === '') return undefined;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}
