import { GRADE_COLOR } from '../lib/labels';
import type { Grade } from '../lib/types';

/**
 * Grade as a large letter in a coloured circle. The letter is always shown (colour is only
 * supplementary) and is large + bold so white on the grade colour meets WCAG AA for large text.
 */
export function GradeBadge({ grade, size = 112 }: { grade: Grade | null; size?: number }) {
  const letter = grade ?? '?';
  const background = grade ? GRADE_COLOR[grade] : '#475569';
  return (
    <div
      role="img"
      aria-label={grade ? `Ocjena ${grade}` : 'Ocjena nije dostupna'}
      data-grade={letter}
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        background,
        color: '#fff',
        display: 'grid',
        placeItems: 'center',
        fontSize: size * 0.55,
        fontWeight: 700,
        lineHeight: 1,
        flexShrink: 0,
      }}
    >
      <span aria-hidden="true">{letter}</span>
    </div>
  );
}
