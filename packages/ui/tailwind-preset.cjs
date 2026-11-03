/**
 * Tailwind CSS 3 preset for @dt/ui: maps Tailwind theme values to the CSS variables in
 * src/tokens.css, so an app only overrides the brand variables.
 *
 * tailwind.config.cjs of an app:
 *   module.exports = {
 *     presets: [require('@dt/ui/tailwind-preset')],
 *     content: ['./index.html', './src/**\/*.{ts,tsx}', '../../../packages/ui/src/**\/*.{ts,tsx}'],
 *   };
 *
 * Spacing: Tailwind's default scale is already 4px-based (1 = 4px), which matches --space-*.
 */
const channel = (name) => `rgb(var(--${name}) / <alpha-value>)`;

module.exports = {
  theme: {
    // Replace (not extend) the type scale: only 14/16/20/24/32/48 px exist.
    fontSize: {
      sm: ['0.875rem', { lineHeight: '1.25rem' }],
      base: ['1rem', { lineHeight: '1.5rem' }],
      lg: ['1.25rem', { lineHeight: '1.75rem' }],
      xl: ['1.5rem', { lineHeight: '2rem' }],
      '2xl': ['2rem', { lineHeight: '2.5rem' }],
      '3xl': ['3rem', { lineHeight: '3.5rem' }],
    },
    extend: {
      colors: {
        neutral: {
          50: channel('neutral-50'),
          100: channel('neutral-100'),
          200: channel('neutral-200'),
          300: channel('neutral-300'),
          400: channel('neutral-400'),
          500: channel('neutral-500'),
          600: channel('neutral-600'),
          700: channel('neutral-700'),
          800: channel('neutral-800'),
          900: channel('neutral-900'),
        },
        brand: { 600: channel('brand-600'), 700: channel('brand-700') },
        accent: { 600: channel('accent-600') },
        success: {
          bg: channel('success-bg'),
          fg: channel('success-fg'),
          border: channel('success-border'),
        },
        warning: {
          bg: channel('warning-bg'),
          fg: channel('warning-fg'),
          border: channel('warning-border'),
        },
        danger: {
          bg: channel('danger-bg'),
          fg: channel('danger-fg'),
          border: channel('danger-border'),
        },
        focus: channel('focus-color'),
      },
      fontFamily: {
        sans: ['var(--font-sans)'],
        mono: ['var(--font-mono)'],
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        DEFAULT: 'var(--radius-md)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        full: 'var(--radius-full)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        DEFAULT: 'var(--shadow-md)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
      },
      ringColor: { DEFAULT: channel('focus-color') },
      ringWidth: { DEFAULT: 'var(--focus-width)' },
      ringOffsetWidth: { DEFAULT: 'var(--focus-offset)' },
    },
  },
};
