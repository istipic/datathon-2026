import type { ReactNode } from 'react';

export interface SkipLinkProps {
  /** Fragment of the element to jump to (default: the main landmark rendered by AppShell). */
  href?: string;
  children?: ReactNode;
}

/** First focusable element on the page: lets keyboard users skip the navigation. */
export function SkipLink({ href = '#main', children = 'Preskoči na sadržaj' }: SkipLinkProps) {
  return (
    <a className="dt-skip-link" href={href}>
      {children}
    </a>
  );
}
