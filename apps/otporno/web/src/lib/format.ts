const nf = new Intl.NumberFormat('hr-HR');
const nf1 = new Intl.NumberFormat('hr-HR', { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export const fmtInt = (n: number | null | undefined): string =>
  n == null ? '–' : nf.format(Math.round(n));
export const fmtDec = (n: number | null | undefined): string => (n == null ? '–' : nf1.format(n));

/** Croatian "dan" / "dana": whole 1, 21, 31... -> dan; every other count, and any decimal, -> dana. */
export function pluralDays(n: number): string {
  if (!Number.isInteger(n)) return 'dana';
  return n % 10 === 1 && n % 100 !== 11 ? 'dan' : 'dana';
}

export const fmtPct = (x: number | null | undefined): string =>
  x == null ? '–' : `${Math.round(x * 100)} %`;
