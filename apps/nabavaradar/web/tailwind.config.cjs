/** Tailwind 3 with the shared @dt/ui preset (tokens map to CSS variables). */
module.exports = {
  presets: [require('@dt/ui/tailwind-preset')],
  content: ['./index.html', './src/**/*.{ts,tsx}', '../../../packages/ui/src/**/*.{ts,tsx}'],
};
