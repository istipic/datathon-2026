#!/usr/bin/env node
/* global process, console */
// Screenshots of the planner before/after the suggested sites. node scripts/planner-shots.mjs <outDir>
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from '@playwright/test';

const out = resolve(process.argv[2] ?? 'planner');
const base = process.env.BASE ?? 'http://127.0.0.1:5173';
mkdirSync(out, { recursive: true });
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
await page.goto(base + '/planiranje', { waitUntil: 'load' });
await page.waitForTimeout(6000);
await shot('before');
await page.getByRole('button', { name: 'Predloži lokacije' }).click();
await page.waitForTimeout(500);
await shot('mid');
await page.waitForTimeout(3500);
await shot('after');
console.log(await page.getByTestId('headline-count').innerText());
await browser.close();
