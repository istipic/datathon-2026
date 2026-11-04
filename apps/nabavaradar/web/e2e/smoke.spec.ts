import { expect, test } from '@playwright/test';

/**
 * Smoke tests against the real stack (API + ingested data).
 *
 * OIB 45050126417 is KONČAR - Elektroindustrija d.d., a company listed on the Zagreb Stock Exchange
 * whose OIB is printed in its official issuer filings (source and excerpt:
 * apps/nabavaradar/data/evidence/2026-11-04_e2e_company_oib_source.json).
 */
const OIB = '45050126417';
const MAILPIT = process.env.MAILPIT_URL ?? 'http://127.0.0.1:8025';

test('home: inline OIB validation, then a real company shows ranked tenders with explanations', async ({
  page,
}) => {
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'Natječaji koji odgovaraju tvojoj djelatnosti' }),
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: /Javni naručitelj\? Provjerite tržište/ }),
  ).toBeVisible();

  const input = page.getByLabel('OIB vaše tvrtke');
  const submit = page.getByRole('button', { name: 'Pronađi natječaje' });
  await input.fill('45050126418');
  await expect(page.getByRole('status').first()).toContainText('Kontrolna znamenka');
  await expect(submit).toBeDisabled();

  await input.fill(OIB);
  await expect(submit).toBeEnabled();
  await submit.click();

  await expect(page).toHaveURL(new RegExp(`/tvrtka/${OIB}$`));
  await expect(page.getByRole('heading', { level: 1 })).toContainText('KONČAR');
  await expect(page.getByText('Grad Zagreb', { exact: false }).first()).toBeVisible();
  await expect(page.getByText(/snimka od/)).toBeVisible();

  const cards = page.getByTestId('tender-card');
  await expect(cards.first()).toBeVisible();
  expect(await cards.count()).toBeGreaterThan(3);
  const first = cards.first();
  await expect(first.getByRole('group', { name: /Prilagodba \d+ posto/ })).toBeVisible();
  await expect(first).toContainText(/n=\d+|nema podataka/); // competition chip always shows n
  await first.getByText('Zašto?').click();
  for (const key of ['S', 'C', 'G', 'T']) {
    await expect(first.getByText(new RegExp(`^${key}:`)).first()).toBeVisible();
  }
});

test('company page: filters narrow the list and an impossible filter shows the empty state', async ({
  page,
}) => {
  await page.goto(`/tvrtka/${OIB}`);
  const cards = page.getByTestId('tender-card');
  await expect(cards.first()).toBeVisible();
  await page.getByLabel('Vrijednost od (EUR)').fill('999999999');
  await expect(page.getByText('Nema otvorenih natječaja za ove uvjete')).toBeVisible();
  await page.getByRole('button', { name: 'Očisti filtere' }).first().click();
  await expect(cards.first()).toBeVisible();
});

test('company page: invalid OIB in the URL is rejected without calling the API', async ({
  page,
}) => {
  let called = false;
  page.on('request', (r) => {
    if (r.url().includes('/api/v1/company/')) called = true;
  });
  await page.goto('/tvrtka/12345678901');
  await expect(page.getByText(/Neispravan OIB/)).toBeVisible();
  expect(called).toBe(false);
});

test('notice details: opens from a card and shows competition history for the CPV group', async ({
  page,
}) => {
  await page.goto(`/tvrtka/${OIB}`);
  const link = page.getByTestId('tender-card').first().getByRole('link').first();
  await link.click();
  await expect(page).toHaveURL(/\/natjecaj\/\d+-\d{4}$/);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Konkurencija u sličnim nabavama' }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: /Otvori na TED-u/ })).toBeVisible();
});

test('buyer page: CPV picker + county returns suppliers map, competition and advice', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('link', { name: /Javni naručitelj\? Provjerite tržište/ }).click();
  await expect(page).toHaveURL(/\/narucitelj$/);

  await page.getByLabel('Pretraži CPV po nazivu ili šifri').fill('45');
  const results = page.getByRole('list', { name: 'Rezultati pretrage CPV-a' });
  await expect(results).toBeVisible();
  await results.getByRole('button').first().click();
  await page
    .getByLabel('Županija naručitelja')
    .selectOption({ label: 'Splitsko-dalmatinska županija' });
  await page.getByRole('button', { name: 'Provjeri tržište' }).click();

  await expect(
    page.getByRole('heading', { name: 'Sposobni dobavljači po županijama' }),
  ).toBeVisible();
  const map = page.getByRole('img', { name: /Karta sposobnih dobavljača/ });
  await expect(map).toBeVisible();
  await expect(map.locator('path[data-nuts3]')).toHaveCount(21);
  await expect(
    page.getByRole('table', { name: 'Broj sposobnih dobavljača po županijama' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Povijesna konkurencija' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Preporuke' })).toBeVisible();
});

test('buyer page: free text works too', async ({ page }) => {
  await page.goto('/narucitelj');
  await page.getByLabel('Opis predmeta nabave').fill('održavanje sustava videonadzora u školama');
  await page.getByRole('button', { name: 'Provjeri tržište' }).click();
  await expect(page.getByRole('heading', { name: 'Predloženi CPV kodovi' })).toBeVisible();
  await expect(page.getByRole('img', { name: /Karta sposobnih dobavljača/ })).toBeVisible();
});

test('methodology shows live validation numbers; sources lists the data sources', async ({
  page,
}) => {
  await page.goto('/metodologija');
  await expect(page.getByRole('heading', { name: 'Validacija (uživo)' })).toBeVisible();
  const row = page.getByRole('row', { name: /NabavaRadar \(S\/C\/G\/T\)/ });
  await expect(row).toContainText('%');
  await expect(page.getByRole('row', { name: /Osnovna: Postgres full-text/ })).toContainText('%');

  await page.goto('/izvori');
  await expect(page.getByRole('heading', { name: 'Izvori podataka' })).toBeVisible();
  await expect(page.getByText('Sudski registar', { exact: false }).first()).toBeVisible();
  await expect(page.getByText('TED', { exact: false }).first()).toBeVisible();
});

test('digest sign-up is double opt-in: confirmation e-mail arrives and its link confirms', async ({
  page,
  request,
}) => {
  const email = `e2e-${Date.now()}@example.hr`;
  await page.goto(`/tvrtka/${OIB}`);
  await expect(page.getByTestId('tender-card').first()).toBeVisible();
  await page.getByRole('textbox', { name: 'E-adresa' }).fill(email);
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Pretplati me' }).click();
  await expect(page.getByText(/poslali smo poruku za potvrdu/)).toBeVisible();

  let link = '';
  await expect
    .poll(
      async () => {
        const list = await request.get(`${MAILPIT}/api/v1/search`, {
          params: { query: `to:${email}` },
        });
        const messages = (await list.json()) as { messages?: { ID: string }[] };
        const id = messages.messages?.[0]?.ID;
        if (!id) return '';
        const msg = await (await request.get(`${MAILPIT}/api/v1/message/${id}`)).json();
        link = (msg.Text as string).match(/https?:\/\/\S+pretplata\/potvrda\?token=\S+/)?.[0] ?? '';
        return link;
      },
      { timeout: 20_000 },
    )
    .not.toBe('');

  const url = new URL(link);
  await page.goto(`${url.pathname}${url.search}`);
  await expect(page.getByRole('heading', { name: 'Potvrda pretplate' })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('potvrđena');
});
