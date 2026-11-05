import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const script = resolve(__dirname, '../../scripts/contrast.mjs');

describe('Night Atlas contrast (WCAG 2.1)', () => {
  it('every text/background pair reaches its minimum ratio', () => {
    const run = spawnSync(process.execPath, [script], { encoding: 'utf-8' });
    expect(run.status, `contrast failures:\n${run.stdout}${run.stderr}`).toBe(0);
    expect(run.stdout).toContain('contrast pairs pass');
  });
});
