#!/usr/bin/env node
/* global process, console, window, requestAnimationFrame, performance */
// Measures page frame rate (rAF callbacks per second, MapLibre included) during the map scenes and writes
// JSON evidence. node scripts/measure-fps.mjs <out.json>. Headless Chromium renders WebGL in software
// (SwiftShader), so these numbers are a lower bound of what a machine with a GPU shows.
import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from '@playwright/test';

const out = resolve(process.argv[2] ?? 'fps.json');
const base = process.env.BASE ?? 'http://127.0.0.1:5173';
const URL =
  '/kartica?lat=45.8131&lon=15.9772&persona=starija&q=Trg%20bana%20Jela%C4%8Di%C4%87a%201';
// GPU=1 runs a headed browser with the machine's real GPU; default is headless software rendering
const gpu = Boolean(process.env.GPU);
const browser = await chromium.launch(
  gpu
    ? { headless: false, args: ['--ignore-gpu-blocklist', '--enable-gpu-rasterization'] }
    : { args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] },
);
const page = await (await browser.newContext({ viewport: { width: 1360, height: 850 } })).newPage();

/** Counts rAF callbacks while `action` runs and for `ms` milliseconds after it. */
async function measure(name, ms, action) {
  await page.evaluate(() => {
    window.__fps = {
      frames: 0,
      t0: performance.now(),
      stop: false,
      worst: 0,
      last: performance.now(),
    };
    const loop = (t) => {
      const s = window.__fps;
      if (s.stop) return;
      s.frames += 1;
      s.worst = Math.max(s.worst, t - s.last);
      s.last = t;
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  });
  await action();
  await page.waitForTimeout(ms);
  const r = await page.evaluate(() => {
    const s = window.__fps;
    s.stop = true;
    const secs = (performance.now() - s.t0) / 1000;
    return { frames: s.frames, seconds: secs, fps: s.frames / secs, worstFrameMs: s.worst };
  });
  console.log(name, JSON.stringify(r));
  return { name, ...r };
}

const results = [];
await page.goto(base + URL, { waitUntil: 'load' });
await page.waitForSelector('[data-testid="reach-bar"]', { timeout: 60000 });
await page.waitForTimeout(6000);
results.push(
  await measure('flood replay (2.5 s of animation)', 600, async () => {
    await page.getByRole('button', { name: 'Ponovi animaciju dosega' }).click();
    await page.waitForTimeout(2300);
  }),
);
results.push(
  await measure('route draw and walk', 500, async () => {
    await page
      .getByRole('button', { name: /^Škola|^Osnovna/ })
      .first()
      .click();
    await page.waitForTimeout(4500);
  }),
);
results.push(
  await measure('3D orbit', 500, async () => {
    await page.getByRole('button', { name: '3D', exact: true }).click();
    await page.waitForTimeout(5500);
  }),
);
await page.goto(base + '/planiranje', { waitUntil: 'load' });
await page.waitForSelector('[data-testid="kpi-total"]', { timeout: 60000 });
await page.waitForTimeout(5000);
results.push(
  await measure(
    'planner columns before -> after (idle map, then 0.9 s animation)',
    1500,
    async () => {
      await page.getByRole('button', { name: 'Predloži lokacije' }).click();
      await page.waitForTimeout(1000);
    },
  ),
);
await browser.close();
writeFileSync(
  out,
  JSON.stringify(
    {
      measured_at: new Date().toISOString(),
      renderer: gpu
        ? 'headed Chromium with the machine GPU'
        : 'headless Chromium, WebGL via SwiftShader (software); lower bound for GPU machines',
      viewport: '1360x850',
      results,
    },
    null,
    2,
  ) + '\n',
);
console.log('wrote', out);
