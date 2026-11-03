import type { ReactNode } from 'react';

export interface EmptyStateProps {
  title: string;
  body?: ReactNode;
  /** Optional call to action (e.g. a button or link). */
  action?: ReactNode;
}

/** Shown when a query succeeded but returned nothing. */
export function EmptyState({ title, body, action }: EmptyStateProps) {
  return (
    <section className="dt-state" aria-live="polite">
      <h2 className="dt-state__title">{title}</h2>
      {body ? <p className="dt-state__body">{body}</p> : null}
      {action}
    </section>
  );
}
