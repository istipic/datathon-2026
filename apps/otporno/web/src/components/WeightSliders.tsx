import { useId } from 'react';

export type Weights = { flood: number; heat: number; fire: number };

interface Props {
  weights: Weights;
  /** Hazards that have data; the others are listed but their weight is renormalised away by the API. */
  available: Record<keyof Weights, boolean>;
  onChange: (w: Weights) => void;
}

const LABELS: Record<keyof Weights, string> = { flood: 'Poplava', heat: 'Vrućina', fire: 'Požar' };

/** Moving one weight rescales the other two proportionally, so the sum stays 1 (the API accepts 1 ± 0.01). */
export function rebalance(w: Weights, key: keyof Weights, value: number): Weights {
  const v = Math.min(1, Math.max(0, value));
  const others = (Object.keys(w) as (keyof Weights)[]).filter((k) => k !== key);
  const rest = others.reduce((s, k) => s + w[k], 0);
  const out = { ...w, [key]: v } as Weights;
  for (const k of others) out[k] = rest > 0 ? (w[k] / rest) * (1 - v) : (1 - v) / others.length;
  const round = (x: number) => Math.round(x * 100) / 100;
  const r = { flood: round(out.flood), heat: round(out.heat), fire: round(out.fire) };
  r[others[1] as keyof Weights] = round(1 - r[key] - r[others[0] as keyof Weights]);
  return r;
}

export function WeightSliders({ weights, available, onChange }: Props) {
  const id = useId();
  return (
    <fieldset className="grid gap-3 border-0 p-0">
      <legend className="text-base font-bold">Težine opasnosti u prioritetu</legend>
      {(Object.keys(LABELS) as (keyof Weights)[]).map((k) => (
        <div key={k}>
          <label htmlFor={`${id}-${k}`} className="flex justify-between text-sm font-bold">
            <span>
              {LABELS[k]}
              {available[k] ? '' : ' (nema podataka, preraspodjeljuje se)'}
            </span>
            <span className="ot-num">{Math.round(weights[k] * 100)} %</span>
          </label>
          <input
            id={`${id}-${k}`}
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={weights[k]}
            onChange={(e) => onChange(rebalance(weights, k, Number(e.target.value)))}
          />
        </div>
      ))}
      <p className="text-sm text-neutral-700">Zbroj težina uvijek je 100 %.</p>
    </fieldset>
  );
}
