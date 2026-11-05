import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import type { Grade } from './types';

/** The versioned scoring configuration (`/api/v1/scoring`); cached for the whole session. */
export function useScoring() {
  return useQuery({ queryKey: ['scoring'], queryFn: () => api.scoring(), staleTime: Infinity });
}

/**
 * Letter of a 0..1 category score on the same A–E scale the API uses for the index
 * (thresholds come from scoring.yaml via `/scoring`, never hard-coded).
 */
export function gradeOfScore(
  score: number,
  grades: Record<string, number> | undefined,
): Grade | null {
  if (!grades) return null;
  const points = score * 100;
  for (const letter of ['A', 'B', 'C', 'D'] as const) {
    const min = grades[letter];
    if (min !== undefined && points >= min) return letter;
  }
  return 'E';
}
