import { expect, test } from '@playwright/test';

test('address -> passport with three hazard cards, cited steps and the HV flood map', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('izložena poplavi i vrućini');

  await page
    .getByRole('combobox', { name: /Adresa bilo gdje u Hrvatskoj/ })
    .fill('Trg bana Josipa Jelačića, Karlovac');
  const first = page.getByRole('option').first();
  await expect(first).toBeVisible({ timeout: 30_000 }); // debounce 400 ms + live geocode
  await first.click();

  await expect(page).toHaveURL(/\/putovnica\?lat=.*&lon=.*/);
  await expect(page.getByRole('heading', { level: 2, name: 'Poplava', exact: true })).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByRole('heading', { level: 2, name: 'Vrućina', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'Požar', exact: true })).toBeVisible();
  // flood: honest "not available, look at the map" with the HV disclaimer
  await expect(
    page.getByText('Automatska procjena nije dostupna; pogledajte kartu.'),
  ).toBeVisible();
  await expect(
    page.getByText(/Hrvatske vode ne jamče za posljedice korištenja/).first(),
  ).toBeVisible();
  // heat: either a band or the explicit quota message, never an empty card
  const heat = page.locator('article[aria-labelledby="card-heat"]');
  await expect(heat).toContainText(/Razina|razina|nije dostupna/);
  // cited steps
  const todo = page.getByRole('region', { name: 'Što učiniti' });
  expect(await todo.getByRole('link').count()).toBeGreaterThanOrEqual(5);
  await expect(todo.getByRole('link').first()).toHaveAttribute('href', /^https:\/\//);
  // map with the overlay controls
  await expect(page.locator('canvas.maplibregl-canvas').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByLabel(/Prozirnost sloja poplava/)).toBeVisible();
  await page.getByRole('checkbox', { name: /Mala vjerojatnost/ }).check();
});

test('outside Croatia the passport explains itself', async ({ page }) => {
  await page.goto('/putovnica?lat=48.8566&lon=2.3522&q=Pariz');
  await expect(page.getByRole('alert')).toContainText('nije unutar Hrvatske', { timeout: 30_000 });
});

test('municipality -> KPIs, priority map and the cooling-centre optimiser runs', async ({
  page,
}) => {
  await page.goto('/opcina');
  await page.getByLabel('Naziv općine ili grada').fill('Karlovac');
  await page
    .getByRole('link', { name: /Karlovac.*stanovnika/ })
    .first()
    .click();
  await expect(page).toHaveURL(/\/opcina\/HR_01791/);
  await expect(page.getByRole('heading', { level: 1, name: 'Karlovac' })).toBeVisible({
    timeout: 30_000,
  });
  const tiles = page.getByRole('region', { name: 'Ključni pokazatelji' });
  await expect(tiles).toContainText('49.669');
  await expect(page.locator('canvas.maplibregl-canvas').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('table', { name: /Stanovnici po razini/ })).toBeVisible();

  await page.getByRole('button', { name: 'Predloži lokacije' }).click();
  await expect(page.getByText(/Pokriveno je/)).toBeVisible({ timeout: 30_000 });
  await expect(
    page
      .getByRole('list')
      .filter({ has: page.getByText(/stanovnika 65\+/) })
      .first(),
  ).toBeVisible();
});
