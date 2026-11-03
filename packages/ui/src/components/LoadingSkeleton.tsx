export interface LoadingSkeletonProps {
  /** Number of placeholder lines (default 3). */
  lines?: number;
  /** Accessible text announced to screen readers. */
  label?: string;
}

/** Placeholder while data loads. Announced politely; animation stops under reduced motion. */
export function LoadingSkeleton({ lines = 3, label = 'Učitavanje…' }: LoadingSkeletonProps) {
  return (
    <div role="status" aria-live="polite" aria-busy="true" className="dt-skeleton">
      <span className="dt-sr-only">{label}</span>
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="dt-skeleton__line"
          aria-hidden="true"
          style={{ width: i === lines - 1 ? '60%' : '100%' }}
        />
      ))}
    </div>
  );
}
