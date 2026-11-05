import type { Grade } from '../lib/types';

/**
 * Grade as a large letter in a glowing ring. The letter is always shown (colour only supports it);
 * the colour comes from `[data-grade]` in index.css and is checked by scripts/contrast.mjs.
 */
export function GradeBadge({ grade, size = 84 }: { grade: Grade | null; size?: number }) {
  const letter = grade ?? '?';
  return (
    <div
      role="img"
      aria-label={grade ? `Ocjena ${grade}` : 'Ocjena nije dostupna'}
      data-grade={letter}
      className="na-ring"
      style={{ width: size, height: size, fontSize: size * 0.52, flexShrink: 0 }}
    >
      <span aria-hidden="true">{letter}</span>
    </div>
  );
}
