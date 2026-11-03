import type { ReactNode } from 'react';
import type { CategoryId } from '../lib/types';

// Simple 24x24 stroke icons (decorative: the label is always shown next to them).
const PATHS: Record<CategoryId, ReactNode> = {
  lijecnik: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="4" />
      <path d="M12 7.5v9M7.5 12h9" />
    </>
  ),
  ljekarna: (
    <>
      <rect x="3.5" y="8.5" width="17" height="7" rx="3.5" transform="rotate(-35 12 12)" />
      <path d="M9.9 9.2l4.2 5.6" />
    </>
  ),
  vrtic: (
    <>
      <path d="M3 11l9-6 9 6v9H3z" />
      <path d="M9 20v-5h6v5M12 9.3l.7 1.4 1.5.2-1.1 1 .3 1.5-1.4-.8-1.4.8.3-1.5-1.1-1 1.5-.2z" />
    </>
  ),
  skola: (
    <>
      <path d="M2.5 9L12 4.5 21.5 9 12 13.5z" />
      <path d="M6 11.2v4.3c0 1.4 2.7 2.7 6 2.7s6-1.3 6-2.7v-4.3M21.5 9v5" />
    </>
  ),
  knjiznica: (
    <>
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z" />
      <path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5" />
    </>
  ),
  posta: (
    <>
      <rect x="3" y="5.5" width="18" height="13" rx="2" />
      <path d="M3.5 7l8.5 6.5L20.5 7" />
    </>
  ),
  prijevoz: (
    <>
      <rect x="5" y="3.5" width="14" height="13" rx="3" />
      <path d="M5 11h14M8.5 20l-1.5 1.5M15.5 20l1.5 1.5M8 16.5V20h8v-3.5" />
      <circle cx="8.8" cy="13.8" r=".6" />
      <circle cx="15.2" cy="13.8" r=".6" />
    </>
  ),
  park: (
    <>
      <path d="M12 21v-6M12 15c-4 0-6-2.7-6-5.5 0-1.8 1-3.2 2.4-3.8C9 4 10.3 3 12 3s3 1 3.6 2.7C17 6.3 18 7.7 18 9.5c0 2.8-2 5.5-6 5.5z" />
    </>
  ),
  namirnice: (
    <>
      <path d="M3 9h18l-2 10.5a1.5 1.5 0 0 1-1.5 1.2h-11A1.5 1.5 0 0 1 5 19.5z" />
      <path d="M8 9l3-5M16 9l-3-5" />
    </>
  ),
};

export function CategoryIcon({ category, size = 24 }: { category: CategoryId; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[category]}
    </svg>
  );
}
