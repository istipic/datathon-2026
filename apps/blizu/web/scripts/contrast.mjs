#!/usr/bin/env node
/* global process, console */
// Checks the Night Atlas palette of src/index.css against WCAG 2.1:
// text >= 4.5:1, large text and UI borders >= 3:1 (muted text must reach 7:1 on the canvas).
// Colours are read from the real stylesheet (the screen :root block, before the print block), so the
// check cannot drift from what ships. Exit code 1 and a table of failures when a pair is too low.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(resolve(here, '../src/index.css'), 'utf-8');
const screenCss = css.slice(0, css.indexOf('@media print'));

/** "--name: 12 34 56;" -> [12, 34, 56] (first occurrence in the screen block). */
function channels(name) {
  const m = new RegExp(`--${name}:\\s*(\\d+)\\s+(\\d+)\\s+(\\d+)`).exec(screenCss);
  if (!m) throw new Error(`token --${name} not found in index.css`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

const lin = (v) => {
  const s = v / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
};
const luminance = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
export function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
/** Alpha-composite fg over bg. */
const over = (fg, bg, alpha) => fg.map((c, i) => Math.round(c * alpha + bg[i] * (1 - alpha)));

const t = Object.fromEntries(
  [
    'na-bg',
    'na-surface-1',
    'na-surface-2',
    'na-text',
    'na-muted',
    'na-accent',
    'na-accent-2',
    'na-edge',
    'na-grade-a',
    'na-grade-b',
    'na-grade-c',
    'na-grade-d',
    'na-grade-e',
    'brand-600',
    'brand-700',
    'accent-600',
    'warning-bg',
    'warning-fg',
    'danger-bg',
    'danger-fg',
    'success-bg',
    'success-fg',
  ].map((n) => [n, channels(n)]),
);
const white = [255, 255, 255];
const surfaces = ['na-bg', 'na-surface-1', 'na-surface-2'];

/** [label, foreground, background, minimum ratio] */
export function pairs() {
  const rows = [];
  for (const s of surfaces) {
    rows.push([`text on ${s}`, t['na-text'], t[s], 7]);
    rows.push([`muted text on ${s}`, t['na-muted'], t[s], s === 'na-bg' ? 7 : 4.5]);
    rows.push([`accent (links, focus) on ${s}`, t['na-accent'], t[s], 4.5]);
    rows.push([`accent-2 on ${s}`, t['na-accent-2'], t[s], 4.5]);
    rows.push([`control border on ${s}`, t['na-edge'], t[s], 3]);
    for (const g of ['a', 'b', 'c', 'd', 'e']) {
      rows.push([`grade ${g.toUpperCase()} on ${s}`, t[`na-grade-${g}`], t[s], 3]);
      rows.push([`bg text on grade ${g.toUpperCase()} chip`, t['na-bg'], t[`na-grade-${g}`], 4.5]);
    }
  }
  // glass: 4 % white over the canvas, with text on top
  const glass = over(white, t['na-bg'], 0.04);
  rows.push(['text on glass', t['na-text'], glass, 7]);
  rows.push(['muted text on glass', t['na-muted'], glass, 4.5]);
  // primary button: dark text on the white pill; accent pill; selected tile
  rows.push(['dark text on white pill', t['na-bg'], white, 7]);
  rows.push(['dark text on accent pill', t['na-bg'], t['na-accent'], 7]);
  // shared @dt/ui slots that still render in the app
  rows.push(['white on brand-600', white, t['brand-600'], 4.5]);
  rows.push(['white on brand-700', white, t['brand-700'], 4.5]);
  rows.push(['white on accent-600', white, t['accent-600'], 4.5]);
  rows.push(['warning chip', t['warning-fg'], t['warning-bg'], 4.5]);
  rows.push(['danger chip', t['danger-fg'], t['danger-bg'], 4.5]);
  rows.push(['success chip', t['success-fg'], t['success-bg'], 4.5]);
  return rows;
}

export function check() {
  return pairs().map(([label, fg, bg, min]) => ({
    label,
    min,
    ratio: ratio(fg, bg),
    ok: ratio(fg, bg) >= min,
  }));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const results = check();
  const bad = results.filter((r) => !r.ok);
  for (const r of results) {
    console.log(
      `${r.ok ? 'ok  ' : 'FAIL'} ${r.ratio.toFixed(2).padStart(6)}:1 (min ${r.min})  ${r.label}`,
    );
  }
  if (bad.length > 0) {
    console.error(`\n${bad.length} contrast pair(s) below the minimum`);
    process.exit(1);
  }
  console.log(`\nall ${results.length} contrast pairs pass`);
}
