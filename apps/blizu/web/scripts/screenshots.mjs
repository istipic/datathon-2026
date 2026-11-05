#!/usr/bin/env node
/* global process, console */
// Takes screenshots of Blizu screens for design review: node scripts/screenshots.mjs <outDir> [baseUrl]
// Needs the dev stack (web + API) running. Viewports: desktop 1360x850 and phone 390x844.
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from '@playwright/test';

const out = resolve(process.argv[2] ?? 'shots');
const base = process.argv[3] ?? 'http://127.0.0.1:5173';
mkdirSync(out, { recursive: true });

const TRG =
  '/kartica?lat=45.81277&lon=15.97659&persona=starija&q=Trg%20bana%20Jela%C4%8Di%C4%87a%201';
const SHOTS = [
  { name: 'home', url: '/' },
  { name: 'results', url: TRG, wait: 6000 },
  { name: 'planner', url: '/planiranje', wait: 6000 },
  { name: 'methodology', url: '/metodologija' },
  { name: 'ui', url: '/__ui' },
  ...(process.env.EXTRA ? JSON.parse(process.env.EXTRA) : []),
];
const VIEWPORTS = [
  { tag: 'd', width: 1360, height: 850 },
  { tag: 'm', width: 390, height: 844 },
];
const only = process.env.ONLY?.split(',');

const browser = await chromium.launch({
  args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'],
});
for (const vp of VIEWPORTS) {
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
  const page = await context.newPage();
  for (const shot of SHOTS) {
    if (only && !only.includes(shot.name)) continue;
    await page.goto(base + shot.url, { waitUntil: 'networkidle' }).catch(() => undefined);
    await page.waitForTimeout(shot.wait ?? 1200);
    const file = resolve(out, `${shot.name}-${vp.tag}.png`);
    await page.screenshot({
      path: file,
      fullPage: shot.name === 'home' || shot.name === 'ui' || shot.name === 'methodology',
    });
    console.log(file);
  }
  await context.close();
}
await browser.close();
