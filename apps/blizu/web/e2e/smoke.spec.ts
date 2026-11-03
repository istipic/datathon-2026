import { expect, test } from '@playwright/test';

test('home -> type address -> pick result -> card shows grade and 9 category rows', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Što ti je blizu?' })).toBeVisible();

  const input = page.getByRole('combobox', { name: 'Adresa u Zagrebu' });
  await input.fill('Ilica 200');
  const first = page.getByRole('option').first();
  await expect(first).toBeVisible({ timeout: 30_000 }); // debounce 400 ms + live geocode
  await first.click();

  await expect(page).toHaveURL(/\/kartica\?lat=.*&lon=.*&persona=opce/);
  const grade = page.locator('[data-grade]').first();
  await expect(grade).toBeVisible();
  await expect(grade).toHaveAttribute('data-grade', /^[A-E]$/);
  await expect(page.locator('li[data-category]')).toHaveCount(9);
  await expect(page.getByTestId('index')).toContainText('/ 100');
  // every category shows minutes in the monospace column
  await expect(page.getByTestId('minutes-ljekarna')).toContainText('min');
  await expect(page.getByTestId('data-note')).toContainText('OpenStreetMap');
});

test('persona switch re-fetches without a page reload', async ({ page }) => {
  await page.goto(
    '/kartica?lat=45.81277&lon=15.97659&persona=opce&q=Trg%20bana%20Jela%C4%8Di%C4%87a',
  );
  await expect(page.locator('li[data-category]')).toHaveCount(9);
  const before = await page.getByTestId('minutes-ljekarna').innerText();
  await page.evaluate(() => ((window as unknown as { __marker: string }).__marker = 'same-page'));
  await page.getByRole('radio', { name: /Starija osoba/ }).click();
  await expect(page).toHaveURL(/persona=starija/);
  await expect(page.getByTestId('minutes-ljekarna')).not.toHaveText(before);
  expect(await page.evaluate(() => (window as unknown as { __marker?: string }).__marker)).toBe(
    'same-page',
  );
});

test('card shows the map with an attribution and a source on demand', async ({ page }) => {
  await page.goto('/kartica?lat=45.78044&lon=15.97217&persona=opce&q=Avenija%20Dubrovnik%2015');
  await expect(page.locator('li[data-category]')).toHaveCount(9);
  await expect(page.getByRole('region', { name: /Karta/ })).toBeVisible();
  await page.getByRole('button', { name: 'Izvor podataka: Ljekarna' }).click();
  await expect(page.getByTestId('source-ljekarna')).toContainText('OpenStreetMap');
});

test('planner shows a legend and runs the optimiser', async ({ page }) => {
  await page.goto('/planiranje');
  await expect(page.getByTestId('kpi-total')).not.toHaveText('', { timeout: 30_000 });
  await expect(page.getByTestId('legend-class').first()).toBeVisible();
  expect(await page.getByTestId('legend-class').count()).toBeGreaterThanOrEqual(2);

  await page.getByRole('button', { name: 'Predloži lokacije' }).click();
  const result = page.getByTestId('optimise-result');
  await expect(result).toBeVisible({ timeout: 30_000 });
  const num = async (id: string) =>
    Number((await page.getByTestId(id).innerText()).replace(/[^\d]/g, ''));
  expect(await num('kpi-after')).toBeGreaterThanOrEqual(await num('kpi-before'));
  await expect(result.locator('ol li')).toHaveCount(3);
});

test('methodology renders the scoring weights and sources page lists every source', async ({
  page,
}) => {
  await page.goto('/metodologija');
  await expect(page.getByTestId('weights-table')).toBeVisible();
  await expect(page.getByRole('cell', { name: '0,22' }).first()).toBeVisible();
  await page.goto('/izvori');
  const table = page.getByRole('table');
  await expect(table).toBeVisible();
  for (const name of ['Eurostat', 'OpenStreetMap', 'ZET', 'Grad Zagreb']) {
    await expect(table).toContainText(name);
  }
});
