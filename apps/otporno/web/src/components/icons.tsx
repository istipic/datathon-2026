const base = {
  width: 24,
  height: 24,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  focusable: false,
};

export function Logo() {
  return (
    <svg width="34" height="34" viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <rect width="64" height="64" rx="14" fill="#fff" />
      <path
        d="M12 40c6-8 12-8 18 0s12 8 18 0"
        fill="none"
        stroke="#1E3A8A"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <circle cx="46" cy="20" r="7" fill="#C2410C" />
    </svg>
  );
}

export function NavIcon({ name }: { name: 'home' | 'town' | 'book' | 'db' }) {
  switch (name) {
    case 'home':
      return (
        <svg {...base}>
          <path d="M3 11l9-8 9 8" />
          <path d="M5 10v10h14V10" />
        </svg>
      );
    case 'town':
      return (
        <svg {...base}>
          <path d="M3 21V9l6-3v15" />
          <path d="M9 21V4l12 5v12" />
          <path d="M13 12h4M13 16h4" />
        </svg>
      );
    case 'book':
      return (
        <svg {...base}>
          <path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2z" />
          <path d="M4 21V5" />
        </svg>
      );
    default:
      return (
        <svg {...base}>
          <ellipse cx="12" cy="6" rx="8" ry="3" />
          <path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6" />
          <path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
        </svg>
      );
  }
}

export function WaveIcon() {
  return (
    <svg {...base} width={28} height={28}>
      <path d="M2 9c3-3 5-3 8 0s5 3 8 0 3-2 4-1" />
      <path d="M2 15c3-3 5-3 8 0s5 3 8 0 3-2 4-1" />
    </svg>
  );
}

export function SunIcon() {
  return (
    <svg {...base} width={28} height={28}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" />
    </svg>
  );
}

export function FlameIcon() {
  return (
    <svg {...base} width={28} height={28}>
      <path d="M12 3c1 4 5 5 5 10a5 5 0 01-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-9z" />
    </svg>
  );
}
