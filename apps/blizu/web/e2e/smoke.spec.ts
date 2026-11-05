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
  await page.getByRole('button', { name: 'Provjeri dostupnost' }).click();

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
  // the vector map (OpenFreeMap) must render: a WebGL canvas, the attribution, and NO raster fallback
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.maplibregl-ctrl-attrib')).toContainText(
    '© OpenStreetMap contributors',
  );
  await page.waitForTimeout(3000);
  await expect(page.getByText(/pričuvna OpenStreetMap karta/)).toHaveCount(0);
  await page
    .getByRole('button', { name: /Ljekarna/ })
    .first()
    .click(); // select the tile: details + source
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

test('compare page shows per-category differences for two addresses', async ({ page }) => {
  await page.goto(
    '/usporedi?a=45.81277,15.97659&b=45.78044,15.97217&persona=opce&aq=Trg%20bana%20Jela%C4%8Di%C4%87a&bq=Avenija%20Dubrovnik%2015',
  );
  await expect(page.getByRole('heading', { name: /Razlika \(B u odnosu na A\)/ })).toBeVisible({
    timeout: 30_000,
  });
  const table = page.getByRole('table');
  await expect(table.locator('tbody tr')).toHaveCount(9);
  await expect(table).toContainText('dalje'); // B (Novi Zagreb) is farther from most services
  await expect(page.locator('[role="img"][data-grade]')).toHaveCount(2);
});

test('the card prints on one A4 page without map and navigation', async ({ page }) => {
  await page.goto('/kartica?lat=45.78044&lon=15.97217&persona=opce&q=Avenija%20Dubrovnik%2015');
  await expect(page.locator('li[data-category]')).toHaveCount(9);
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('.dt-header')).toBeHidden();
  await expect(page.locator('.maplibregl-map')).toBeHidden();
  const pdf = await page.pdf({ preferCSSPageSize: true, printBackground: true });
  const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) ?? []).length;
  expect(pages).toBe(1);
});
