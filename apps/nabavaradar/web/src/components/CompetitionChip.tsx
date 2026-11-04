import { formatNumber, formatPercent } from '../lib/format';
import type { CompetitionInfo } from '../lib/types';

/**
 * Competition in similar past awards. The sample size n is always shown; "Niska konkurencija"
 * only when the single-bid share is >= 40 % on at least 10 awards (flag from the API).
 */
export function CompetitionChip({ competition }: { competition: CompetitionInfo }) {
  const { n, flag, median_submissions: median, single_bid_share: share, scope } = competition;
  if (n === 0) {
    return <span className="dt-chip dt-chip--neutral">○ Konkurencija: nema podataka</span>;
  }
  const where = scope === 'HR' ? 'cijela Hrvatska' : `regija ${scope}`;
  const title = `Slične nabave (${where}): medijan ${formatNumber(median)} ponuda, ${formatPercent(share)} s jednom ponudom, n = ${n}`;
  return (
    <span
      className={`dt-chip ${flag ? 'dt-chip--warning' : 'dt-chip--neutral'}`}
      title={title}
      aria-label={title}
    >
      {flag ? '⚠ Niska konkurencija' : '● Konkurencija'}{' '}
      <span className="num">
        · medijan {formatNumber(median)} · n={n}
      </span>
    </span>
  );
}
