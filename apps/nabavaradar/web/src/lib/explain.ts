import { countdown, formatPercent } from './format';
import type { MatchItem } from './types';

/** Plain-language reasons for a match, one sentence per fit component (S, C, G, T). */
export function explain(item: MatchItem): { key: 'S' | 'C' | 'G' | 'T'; text: string }[] {
  const { components: c, best_activity: act } = item;
  const code = act.code ? ` (NKD ${act.code})` : '';
  const division = item.cpv_division_label
    ? `CPV područje ${item.cpv_division} „${item.cpv_division_label}“`
    : `CPV područje ${item.cpv_division ?? '–'}`;

  const s = {
    key: 'S' as const,
    text: `Opisu nabave najviše odgovara djelatnost „${act.label}“${code}; sličnost ${formatPercent(c.S)}.`,
  };
  const cText =
    c.C >= 1
      ? `${division} među 3 je najbližih područja vašem profilu (${item.division_rank}. mjesto).`
      : c.C > 0
        ? `${division} među 10 je najbližih područja vašem profilu (${item.division_rank}. mjesto).`
        : `${division} nije među 10 najbližih područja vašem profilu.`;
  const gText =
    c.G >= 1
      ? 'Naručitelj je u istoj županiji kao sjedište vaše tvrtke.'
      : item.nuts3 === null
        ? 'Lokacija naručitelja nije poznata (neutralna ocjena).'
        : c.G >= 0.5
          ? 'Naručitelj je u istoj regiji (NUTS2), ali u drugoj županiji.'
          : 'Naručitelj je u drugoj regiji.';
  const tText = `Rok: ${countdown(item.days_left)}${
    item.days_left !== null && item.days_left < 15
      ? ' (manje od 15 dana smanjuje ocjenu, ispod 3 dana je nula).'
      : '.'
  }`;
  return [s, { key: 'C', text: cText }, { key: 'G', text: gText }, { key: 'T', text: tText }];
}
