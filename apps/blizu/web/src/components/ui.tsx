import type { ButtonHTMLAttributes, ReactNode } from 'react';

/** 24x24 stroke icons of the Night Atlas system (decorative unless a label is passed). */
const ICONS = {
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  back: <path d="M19 12H5M11 6l-6 6 6 6" />,
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l4.5 4.5" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21s-6.5-6.2-6.5-11a6.5 6.5 0 0 1 13 0c0 4.800-6.500 11-6.500 11z" />
      <circle cx="12" cy="10" r="2.300" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  locate: (
    <>
      <circle cx="12" cy="12" r="3.500" />
      <path d="M12 2.500v3.500M12 18v3.500M2.500 12H6M18 12h3.500" />
    </>
  ),
  layers: (
    <>
      <path d="M12 3l9 5-9 5-9-5z" />
      <path d="M3 13l9 5 9-5" />
    </>
  ),
  cube: (
    <>
      <path d="M12 3l8.500 4.800v8.400L12 21l-8.500-4.800V7.800z" />
      <path d="M12 12.500v8.500M12 12.500L3.800 7.800M12 12.500l8.200-4.700" />
    </>
  ),
  play: <path d="M7 4.500v15l12-7.500z" />,
  replay: (
    <>
      <path d="M4 12a8 8 0 1 0 2.600-5.900" />
      <path d="M4 4v4.500h4.500" />
    </>
  ),
  chevron: <path d="M6 9l6 6 6-6" />,
  walk: (
    <>
      <circle cx="13" cy="4.500" r="1.800" />
      <path d="M10.500 21l2-6.500-2.500-2.500 1-4.500 3 2.500 2.500.5M10 8.500L7.500 11" />
      <path d="M12.500 14.500l3.500 2 .5 4.500" />
    </>
  ),
  person: (
    <>
      <circle cx="12" cy="7.500" r="3.500" />
      <path d="M5 20c.8-4 3.500-6 7-6s6.200 2 7 6" />
    </>
  ),
  elder: (
    <>
      <circle cx="10" cy="5" r="2" />
      <path d="M9 21l1.500-7-2-2.500 1-4.500 3 2 3 .5M18 11v10" />
    </>
  ),
  parent: (
    <>
      <circle cx="9" cy="5" r="2" />
      <path d="M6 21v-8l-1.500-3M6 13h5l1.500 3v5" />
      <circle cx="17" cy="12" r="1.500" />
      <path d="M17 14.500V21" />
    </>
  ),
  wheelchair: (
    <>
      <circle cx="10" cy="4.500" r="1.800" />
      <path d="M10 7.500v6h5l2.500 5M10 10.500h5" />
      <path d="M7.500 12.500a5 5 0 1 0 6.500 6.500" />
    </>
  ),
  alert: (
    <>
      <path d="M12 3.500l9.500 16.500h-19z" />
      <path d="M12 10v4.500M12 17.500h.01" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof ICONS;

export function Icon({
  name,
  size = 20,
  filled,
}: {
  name: IconName;
  size?: number;
  filled?: boolean;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {ICONS[name]}
    </svg>
  );
}

/** Logo mark: a walking-distance ring around a pin, dark on a white rounded square. */
export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <span className="na-brand__mark" style={{ width: size, height: size }} aria-hidden="true">
      <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="9.500" stroke="currentColor" strokeWidth="2" opacity="0.35" />
        <circle cx="12" cy="12" r="5.500" stroke="currentColor" strokeWidth="2" opacity="0.65" />
        <circle cx="12" cy="12" r="2.200" fill="currentColor" />
      </svg>
    </span>
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'accent';
  size?: 'md' | 'sm';
  /** Trailing arrow of the primary call to action. */
  arrow?: boolean;
  loading?: boolean;
}

/** White pill (primary), ghost or cyan button with all states: hover, focus-visible, active, disabled, loading. */
export function Button({
  variant = 'primary',
  size = 'md',
  arrow,
  loading,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  const cls = [
    'na-btn',
    variant === 'ghost' ? 'na-btn--ghost' : variant === 'accent' ? 'na-btn--accent' : '',
    size === 'sm' ? 'na-btn--sm' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button
      type={type}
      className={cls}
      disabled={disabled || loading}
      data-loading={loading ? 'true' : undefined}
      {...rest}
    >
      {loading ? <span className="na-spinner" aria-hidden="true" /> : null}
      {children}
      {arrow && !loading ? (
        <span className="na-btn__arrow" aria-hidden="true">
          <Icon name="arrow" size={18} />
        </span>
      ) : null}
    </button>
  );
}

export function Chip({ children, warn }: { children: ReactNode; warn?: boolean }) {
  return <span className={warn ? 'na-chip na-chip--warn' : 'na-chip'}>{children}</span>;
}
