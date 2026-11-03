const fmt = new Intl.DateTimeFormat('hr-HR', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Europe/Zagreb',
});

/** Format an ISO timestamp for display in Croatian (Europe/Zagreb); null for missing/invalid. */
export function formatDateTimeHr(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : fmt.format(date);
}
