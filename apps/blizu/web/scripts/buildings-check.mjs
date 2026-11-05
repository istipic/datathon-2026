#!/usr/bin/env node
/* global process, console, window */
// Verifies in the real OpenFreeMap tiles over Zagreb that `building` features carry render_height /
// render_min_height, and writes the evidence. node scripts/buildings-check.mjs <out.json>
import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from '@playwright/test';

const out = resolve(process.argv[2] ?? 'buildings.json');
const base = process.env.BASE ?? 'http://127.0.0.1:5173';
const browser = await chromium.launch({
  args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'],
});
const page = await (await browser.newContext({ viewport: { width: 1360, height: 850 } })).newPage();
await page.goto(`${base}/kartica?lat=45.8131&lon=15.9772&persona=starija&scena=3d&q=Trg`, {
  waitUntil: 'load',
});
await page.waitForSelector('[data-testid="reach-bar"]', { timeout: 60000 });
await page.waitForTimeout(9000);
const result = await page.evaluate(() => {
  const map = window.__blizuMap;
  const feats = map.queryRenderedFeatures({ layers: ['na-buildings'] });
  const withHeight = feats.filter((f) => typeof f.properties.render_height === 'number');
  const heights = withHeight.map((f) => f.properties.render_height).sort((a, b) => a - b);
  const withMin = feats.filter((f) => typeof f.properties.render_min_height === 'number');
  const sample = feats.slice(0, 5).map((f) => f.properties);
  return {
    zoom: map.getZoom(),
    pitch: map.getPitch(),
    rendered_features: feats.length,
    with_render_height: withHeight.length,
    with_render_min_height: withMin.length,
    height_min_m: heights[0] ?? null,
    height_median_m: heights[Math.floor(heights.length / 2)] ?? null,
    height_max_m: heights.at(-1) ?? null,
    sample_properties: sample,
  };
});
console.log(JSON.stringify(result, null, 2));
writeFileSync(
  out,
  JSON.stringify(
    {
      checked_at: new Date().toISOString(),
      style: 'https://tiles.openfreemap.org/styles/dark',
      source: 'openmaptiles / building (OpenFreeMap planet tiles)',
      origin: 'Trg bana Jelačića, Zagreb (45.8131, 15.9772)',
      ...result,
    },
    null,
    2,
  ) + '\n',
);
await browser.close();
