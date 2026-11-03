export type ConfidenceLevel = 'visoka' | 'srednja' | 'niska';

export interface ConfidenceBadgeProps {
  level: ConfidenceLevel;
}

const CONFIG: Record<ConfidenceLevel, { chip: string; dots: string }> = {
  visoka: { chip: 'success', dots: '●●●' },
  srednja: { chip: 'warning', dots: '●●○' },
  niska: { chip: 'danger', dots: '●○○' },
};

/** Confidence of a derived value. Level is spelled out and shown as filled dots, not by colour alone. */
export function ConfidenceBadge({ level }: ConfidenceBadgeProps) {
  const { chip, dots } = CONFIG[level];
  return (
    <span className={`dt-chip dt-chip--${chip}`} data-level={level}>
      <span aria-hidden="true">{dots}</span>
      <span>Pouzdanost: {level}</span>
    </span>
  );
}
