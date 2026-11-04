import { COMPONENT_LABELS, formatPercent } from '../lib/format';
import type { MatchItem } from '../lib/types';

/** The overall fit as a number plus a bar (the number carries the meaning, not the colour). */
export function FitBar({ fit }: { fit: number }) {
  const pct = Math.round(fit * 100);
  return (
    <div className="nr-fit" role="group" aria-label={`Prilagodba ${pct} posto`}>
      <span className="nr-fit__value num">{pct} %</span>
      <span className="nr-bar" aria-hidden="true">
        <span style={{ width: `${pct}%` }} />
      </span>
    </div>
  );
}

const WEIGHT = { S: 0.55, C: 0.25, G: 0.1, T: 0.1 } as const;

/** S / C / G / T with their weights, one bar each. */
export function ComponentBars({ components }: { components: MatchItem['components'] }) {
  return (
    <div role="list" aria-label="Sastavnice prilagodbe">
      {(['S', 'C', 'G', 'T'] as const).map((key) => (
        <div className="nr-comp-row" role="listitem" key={key}>
          <span>
            <strong>{key}</strong> · {COMPONENT_LABELS[key]}{' '}
            <span className="num text-neutral-600">({Math.round(WEIGHT[key] * 100)} %)</span>
          </span>
          <span className="nr-bar nr-bar--thin" aria-hidden="true">
            <span style={{ width: `${Math.round(components[key] * 100)}%` }} />
          </span>
          <span className="num text-right">{formatPercent(components[key])}</span>
        </div>
      ))}
    </div>
  );
}
