import { expect, test, type Page } from '@playwright/test';

// Real stack: Trg bana Jelačića, persona "starija". Dev-only hooks: window.__blizuAnim, window.__blizuMap.
const URL =
  '/kartica?lat=45.8131&lon=15.9772&persona=starija&q=Trg%20bana%20Jela%C4%8Di%C4%87a%201';

type Hooks = {
  __blizuAnim?: { frames: number; running: boolean };
  __blizuMap?: {
    getPitch(): number;
    querySourceFeatures(id: string): unknown[];
  };
};
const frames = (page: Page) =>
  page.evaluate(() => (window as unknown as Hooks).__blizuAnim?.frames ?? 0);
const running = (page: Page) =>
  page.evaluate(() => (window as unknown as Hooks).__blizuAnim?.running ?? null);

async function openResults(page: Page) {
  await page.goto(URL);
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('reach-bar')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('reach-counter')).toContainText('U dosegu', { timeout: 30_000 });
}

test('flood runs on the shared clock and the slider changes the counter from the API counts', async ({
  page,
}) => {
  await openResults(page);
  await page.getByRole('button', { name: 'Ponovi animaciju dosega' }).click();
  const before = await frames(page);
  await page.waitForTimeout(600);
  expect(await frames(page)).toBeGreaterThan(before);

  // let the flood come to rest, then drive the slider to 5 minutes
  await expect(page.getByTestId('reach-live')).toContainText('U dosegu 15 minuta', {
    timeout: 15_000,
  });
  const full = await page.getByTestId('reach-counter').innerText();
  await page.locator('#reach-slider').fill('5');
  await expect(page.getByTestId('reach-counter')).toContainText('U dosegu 5 minuta', {
    timeout: 15_000,
  });
  const five = await page.getByTestId('reach-counter').innerText();
  expect(five).not.toBe(full);
  await expect(page.locator('#reach-slider')).toHaveAttribute('aria-valuetext', '5 minuta');

  // the counts come from the API, not from the client
  const api = await (
    await page.request.get('/api/v1/isochrone?lat=45.8131&lon=15.9772&persona=starija&max_min=15')
  ).json();
  const apiTotal = Object.values(api.counts['5'] as Record<string, number>).reduce(
    (a, b) => a + b,
    0,
  );
  const shownTotal = [...five.matchAll(/(\d+) /g)]
    .slice(1) // skip the "5 minuta" at the start
    .reduce((a, m) => a + Number(m[1]), 0);
  expect(shownTotal).toBe(apiTotal);
});

test('tapping a category draws the route and the tile minutes equal the API minutes', async ({
  page,
}) => {
  await openResults(page);
  await page
    .getByRole('button', { name: /^Ljekarna/ })
    .first()
    .click();
  await expect(page.getByTestId('route-summary')).toBeVisible({ timeout: 30_000 });
  await expect
    .poll(
      () =>
        page.evaluate(() => {
          const map = (window as unknown as Hooks).__blizuMap;
          return ['route-a', 'route-b'].reduce(
            (n, id) => n + (map?.querySourceFeatures(id).length ?? 0),
            0,
          );
        }),
      { timeout: 20_000 },
    )
    .toBeGreaterThan(0);
  const route = await (
    await page.request.get(
      '/api/v1/route?lat=45.8131&lon=15.9772&persona=starija&category=ljekarna',
    )
  ).json();
  await expect(page.getByTestId('minutes-ljekarna')).toHaveText(`${Math.round(route.minutes)} min`);
  await expect(page.getByTestId('route-summary')).toContainText(
    `${Math.round(route.distance_m)} m`,
  );
  await expect(page).toHaveURL(/scena=put/);
});

test('the 3D scene tilts the map', async ({ page }) => {
  await openResults(page);
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect
    .poll(() => page.evaluate(() => (window as unknown as Hooks).__blizuMap?.getPitch() ?? 0), {
      timeout: 20_000,
    })
    .toBeGreaterThanOrEqual(55);
  await expect(page).toHaveURL(/scena=3d/);
});

test('planner: columns, headline equals the API total and the table shows the same numbers', async ({
  page,
}) => {
  await page.goto('/planiranje');
  await expect(page.getByTestId('kpi-total')).not.toHaveText('', { timeout: 30_000 });
  const responsePromise = page.waitForResponse(
    (r) => r.url().includes('/plan/optimise') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Predloži lokacije' }).click();
  const total = (await (await responsePromise).json()).total_newly_covered as number;
  await expect(page.getByTestId('headline-count')).toHaveText(
    new RegExp(`^\\+${total.toLocaleString('hr-HR').replace('.', '\\.')} osoba$`),
    { timeout: 15_000 },
  );
  await expect(page.getByTestId('optimise-table')).toBeVisible();
  await expect(page.getByTestId('optimise-table').locator('tbody tr').first()).toBeVisible();
});

test.describe('reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });

  test('results: no animation loop, final states shown at once, controls still work', async ({
    page,
  }) => {
    await openResults(page);
    expect(await running(page)).toBe(false);
    await expect(page.getByTestId('reach-live')).toContainText('U dosegu 15 minuta');
    await expect(page.locator('#reach-slider')).toHaveValue('15');
    await page.locator('#reach-slider').fill('10');
    await expect(page.getByTestId('reach-counter')).toContainText('U dosegu 10 minuta');
    await page
      .getByRole('button', { name: /^Ljekarna/ })
      .first()
      .click();
    await expect(page.getByTestId('route-summary')).toBeVisible({ timeout: 30_000 });
    expect(await running(page)).toBe(false);
  });

  test('planner: the headline shows the final number immediately', async ({ page }) => {
    await page.goto('/planiranje');
    await expect(page.getByTestId('kpi-total')).not.toHaveText('', { timeout: 30_000 });
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/plan/optimise') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Predloži lokacije' }).click();
    const total = (await (await responsePromise).json()).total_newly_covered as number;
    await expect(page.getByTestId('headline-count')).toContainText(total.toLocaleString('hr-HR'));
    expect(await running(page)).toBe(false);
  });
});
