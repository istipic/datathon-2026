import preset from '../tailwind-preset.cjs';
import componentsCss from './components.css?raw';
import tokensCss from './tokens.css?raw';

/** WCAG 2.1 relative luminance / contrast ratio. */
function luminance([r, g, b]: number[]): number {
  const lin = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r!) + 0.7152 * lin(g!) + 0.0722 * lin(b!);
}
function contrast(a: number[], b: number[]): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}
function token(name: string): number[] {
  const m = new RegExp(`--${name}:\\s*(\\d+)\\s+(\\d+)\\s+(\\d+);`).exec(tokensCss);
  if (!m) throw new Error(`token --${name} not found as RGB channels`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

describe('WCAG 2.1 AA contrast of default tokens', () => {
  const textPairs: [string, string][] = [
    ['neutral-900', 'white'],
    ['neutral-600', 'white'],
    ['neutral-600', 'neutral-50'],
    ['neutral-600', 'neutral-100'],
    ['neutral-700', 'neutral-100'],
    ['white', 'brand-600'],
    ['white', 'brand-700'],
    ['white', 'accent-600'],
    ['brand-700', 'white'],
    ['brand-700', 'neutral-100'],
    ['success-fg', 'success-bg'],
    ['warning-fg', 'warning-bg'],
    ['danger-fg', 'danger-bg'],
    ['neutral-900', 'neutral-200'],
  ];
  it.each(textPairs)('text %s on %s ≥ 4.5:1', (fg, bg) => {
    expect(contrast(token(fg), token(bg))).toBeGreaterThanOrEqual(4.5);
  });

  it.each(['white', 'neutral-50', 'neutral-100'])('focus ring on %s ≥ 3:1', (bg) => {
    expect(contrast(token('focus-color'), token(bg))).toBeGreaterThanOrEqual(3);
  });
});

describe('tokens.css', () => {
  it('defines the brand slots, spacing scale, radius, shadows and focus ring', () => {
    for (const name of [
      '--brand-600',
      '--brand-700',
      '--accent-600',
      '--space-1: 4px',
      '--space-2: 8px',
      '--space-4: 16px',
      '--radius-md',
      '--shadow-md',
      '--focus-ring',
    ]) {
      expect(tokensCss).toContain(name);
    }
  });

  it('defines the 14/16/20/24/32/48 px type scale', () => {
    for (const rem of ['0.875rem', '1rem', '1.25rem', '1.5rem', '2rem', '3rem']) {
      expect(tokensCss).toContain(rem);
    }
  });

  it('uses IBM Plex Sans and Mono', () => {
    expect(tokensCss).toContain("'IBM Plex Sans'");
    expect(tokensCss).toContain("'IBM Plex Mono'");
    expect(componentsCss).toContain('tabular-nums');
  });
});

describe('components.css accessibility rules', () => {
  it('has a visible focus style and a reduced-motion override', () => {
    expect(componentsCss).toContain(':focus-visible');
    expect(componentsCss).toContain('prefers-reduced-motion: reduce');
  });
});

describe('tailwind-preset.cjs', () => {
  it('maps colours to CSS variables with alpha support', () => {
    const colors = preset.theme.extend.colors;
    expect(colors.brand['600']).toBe('rgb(var(--brand-600) / <alpha-value>)');
    expect(colors.accent['600']).toBe('rgb(var(--accent-600) / <alpha-value>)');
    expect(colors.neutral['900']).toBe('rgb(var(--neutral-900) / <alpha-value>)');
  });

  it('replaces the type scale with the six project sizes and maps fonts to the variables', () => {
    expect(Object.keys(preset.theme.fontSize)).toEqual(['sm', 'base', 'lg', 'xl', '2xl', '3xl']);
    expect(preset.theme.extend.fontFamily.mono).toEqual(['var(--font-mono)']);
    expect(preset.theme.extend.ringWidth.DEFAULT).toBe('var(--focus-width)');
  });
});
