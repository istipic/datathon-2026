#!/usr/bin/env node
/* global process, console, window */
// Exploration/evidence script: screenshots of the map scenes. node scripts/scenes.mjs <outDir>
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from '@playwright/test';

const out = resolve(process.argv[2] ?? 'scenes');
const base = process.env.BASE ?? 'http://127.0.0.1:5173';
mkdirSync(out, { recursive: true });
const URL =
  '/kartica?lat=45.8131&lon=15.9772&persona=starija&q=Trg%20bana%20Jela%C4%8Di%C4%87a%201';
const vp = process.env.MOBILE ? { width: 390, height: 844 } : { width: 1360, height: 850 };
const tag = process.env.MOBILE ? 'm' : 'd';

const browser = await chromium.launch({
  args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'],
});
const page = await (await browser.newContext({ viewport: vp })).newPage();
page.on('console', (m) => m.type() === 'error' && console.log('console error:', m.text()));
const shot = async (name) => {
  const file = resolve(out, `${name}-${tag}.png`);
  await page.screenshot({ path: file });
  console.log(file);
};
await page.goto(base + URL, { waitUntil: 'load' });
await page.waitForTimeout(1400);
await shot('flood-mid');
await page.waitForTimeout(9000);
await shot('flood-rest');
await page
  .getByRole('button', { name: /Ljekarna/ })
  .first()
  .click();
await page.waitForTimeout(1800);
await shot('route-draw');
await page.waitForTimeout(6000);
await shot('route-walk');
await page.getByRole('button', { name: '3D', exact: true }).click();
await page.waitForTimeout(4500);
await shot('three-d');
console.log(
  await page.evaluate(() => ({
    pitch: window.__blizuMap?.getPitch(),
    frames: window.__blizuAnim,
  })),
);
await browser.close();
