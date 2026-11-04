import { fmtDec, pluralDays } from '../lib/format';
import type { HeatBlock } from '../lib/types';

interface Props {
  heat: HeatBlock;
}

/**
 * "Danas" (1991.–2020.) against 2031.–2050. as horizontal bars of hot days per year. The future bar
 * carries a whisker for the range between the three climate models. Values are always written out.
 */
export function HeatBars({ heat }: Props) {
  const base = heat.base_hot_days ?? 0;
  const fut = heat.future_hot_days;
  if (!fut) return null;
  const max = Math.max(fut.max, base, 1) * 1.1;
  const pct = (v: number) => `${Math.min(100, (v / max) * 100)}%`;
  return (
    <div className="grid gap-4" role="group" aria-label="Vrući dani godišnje, danas i 2031.–2050.">
      <div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-bold">Danas ({heat.periods?.base ?? '1991.–2020.'})</span>
          <span className="ot-num font-bold">
            {fmtDec(base)} {pluralDays(base)}
          </span>
        </div>
        <div className="mt-1 h-5 rounded bg-neutral-200">
          <div className="h-5 rounded" style={{ width: pct(base), background: '#F9B572' }} />
        </div>
      </div>
      <div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-bold">2031.–2050. (prosjek modela)</span>
          <span className="ot-num font-bold">
            {fmtDec(fut.mean)} {pluralDays(fut.mean)}
          </span>
        </div>
        <div className="relative mt-1 h-5 rounded bg-neutral-200">
          <div className="h-5 rounded" style={{ width: pct(fut.mean), background: '#9A2A0B' }} />
          <div
            aria-hidden="true"
            className="absolute top-1/2 h-0.5 -translate-y-1/2 bg-neutral-900"
            style={{ left: pct(fut.min), width: `calc(${pct(fut.max)} - ${pct(fut.min)})` }}
          />
          <div
            aria-hidden="true"
            className="absolute top-0 h-5 w-0.5 bg-neutral-900"
            style={{ left: pct(fut.min) }}
          />
          <div
            aria-hidden="true"
            className="absolute top-0 h-5 w-0.5 bg-neutral-900"
            style={{ left: pct(fut.max) }}
          />
        </div>
        <p className="mt-1 text-sm text-neutral-700">
          Raspon između tri klimatska modela: {fmtDec(fut.min)}–{fmtDec(fut.max)}{' '}
          {pluralDays(fut.max)} godišnje.
        </p>
      </div>
    </div>
  );
}
