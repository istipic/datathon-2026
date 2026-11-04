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

test('/metodologija is gone: it redirects to the sources page with the quality check', async ({
  page,
}) => {
  await page.goto('/metodologija');
  await expect(page).toHaveURL(/\/izvori$/);
  await expect(page.getByRole('heading', { name: 'Provjera kvalitete' })).toBeVisible();
  const row = page.getByRole('row', { name: /Birokratko \(S\/C\/G\/T\)/ });
  await expect(row).toContainText('%');
  await expect(page.getByRole('row', { name: /Osnovna: pretraživanje teksta/ })).toContainText('%');
  await expect(page.getByRole('heading', { name: 'Izvori podataka' }).first()).toBeVisible();
  await expect(page.getByText('Sudski registar', { exact: false }).first()).toBeVisible();
  await expect(page.getByText('TED', { exact: false }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Metodologija' })).toHaveCount(0);
});

test('home: Neo-Brutalist landing with real numbers, marquee and the alert button', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.getByTestId('hero-badge')).toContainText(/\d+ otvorenih natječaja/);
  await expect(page.getByTestId('hero-example').getByTestId('tender-card')).toBeVisible();
  await expect(page.getByText('Primjer stvarnog natječaja').first()).toBeVisible();
  await expect(page.getByTestId('marquee')).toBeAttached();
  await expect(page.getByRole('heading', { name: 'Česta pitanja' })).toBeVisible();
  // fonts are served by the app itself (the CSP only allows 'self')
  const fonts = await page.evaluate(() => [...document.fonts].map((f) => f.family));
  expect(fonts.join(' ')).toContain('Cabinet Grotesk');
  await page.getByRole('button', { name: 'Pošalji mi relevantne natječaje' }).first().click();
  await expect(page.getByRole('dialog', { name: 'Pošalji mi relevantne natječaje' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('company page: sort, search, save, calendar, CSV, hide and share link', async ({ page }) => {
  await page.goto(`/tvrtka/${OIB}`);
  const cards = page.getByTestId('tender-card');
  await expect(cards.first()).toBeVisible();

  // grouped publications of one procedure are collapsed into one card
  const badges = page.getByTestId('group-badge');
  expect(await badges.count()).toBeGreaterThan(0);

  // sort by deadline: the URL keeps it (share link)
  await page.getByLabel('Poredak').selectOption('deadline');
  await expect(page).toHaveURL(/poredak=deadline/);
  await page.getByLabel('Traži u rezultatima').fill('zzzz-nema-takvog');
  await expect(page.getByText('Nema otvorenih natječaja za ove uvjete')).toBeVisible();
  await page.getByLabel('Traži u rezultatima').fill('');
  await expect(cards.first()).toBeVisible();

  // CSV with BOM
  const [csv] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Izvezi CSV' }).click(),
  ]);
  expect(csv.suggestedFilename()).toBe(`natjecaji-${OIB}.csv`);
  const csvText = await (
    await import('node:fs/promises')
  ).readFile((await csv.path()) as string, 'utf8');
  expect(csvText.charCodeAt(0)).toBe(0xfeff);
  expect(csvText).toContain('Prilagodba (%);Naslov');

  // calendar file of the first card
  const [ics] = await Promise.all([
    page.waitForEvent('download'),
    cards.first().getByRole('button', { name: 'Dodaj rok u kalendar' }).click(),
  ]);
  const icsText = await (
    await import('node:fs/promises')
  ).readFile((await ics.path()) as string, 'utf8');
  expect(icsText).toContain('BEGIN:VEVENT');
  expect(icsText).toContain('TRIGGER:-P1D');

  // save ("Prati"), see it on /spremljeno
  const title = (await cards.first().getByRole('heading').innerText()).trim();
  await cards.first().getByRole('button', { name: /Prati/ }).click();
  await expect(cards.first().getByRole('button', { name: /Pratim/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page
    .getByRole('navigation', { name: 'Glavna navigacija' })
    .getByRole('link', { name: 'Spremljeno' })
    .click();
  await expect(page.getByTestId('saved-card').first()).toContainText(title);
  await page.goBack();

  // "Ne zanima me" hides the notice and remembers it
  const firstPub = await cards.first().getAttribute('data-pub-no');
  await cards.first().getByRole('button', { name: 'Ne zanima me' }).click();
  await expect(page.locator(`[data-pub-no="${firstPub}"]`)).toHaveCount(0);
  await expect(page.getByText(/Sakriveno ste 1 natječaj/)).toBeVisible();
  await page.reload();
  await expect(page.locator(`[data-pub-no="${firstPub}"]`)).toHaveCount(0);
});

test('alerts: subscribe with a threshold, confirm, receive one alert, never the same twice', async ({
  page,
  request,
}) => {
  test.setTimeout(240_000);
  const email = `alert-${Date.now()}@example.hr`;
  const mails = async (query: string) => {
    const list = await request.get(`${MAILPIT}/api/v1/search`, { params: { query } });
    return ((await list.json()) as { messages?: { ID: string; Subject: string }[] }).messages ?? [];
  };
  const text = async (id: string) =>
    ((await (await request.get(`${MAILPIT}/api/v1/message/${id}`)).json()) as { Text: string })
      .Text;

  await page.goto(`/tvrtka/${OIB}`);
  await expect(page.getByTestId('tender-card').first()).toBeVisible();
  await page.getByRole('button', { name: 'Pošalji mi relevantne natječaje' }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('E-adresa', { exact: true }).fill(email);
  await dialog.getByLabel('Prag prilagodbe u postocima', { exact: true }).fill('50');
  await expect(dialog.getByTestId('alert-preview')).toContainText(/danas bi dobili \d+ natječaj/);
  await dialog.getByRole('checkbox', { name: /Pristajem da Birokratko/ }).check();
  await dialog.getByRole('button', { name: 'Pošalji mi relevantne natječaje' }).click();
  await expect(dialog.getByText(/poslali smo poruku za potvrdu/)).toBeVisible();

  let link = '';
  await expect
    .poll(
      async () => {
        const id = (await mails(`to:${email}`))[0]?.ID;
        if (!id) return '';
        link = (await text(id)).match(/https?:\/\/\S+pretplata\/potvrda\?token=\S+/)?.[0] ?? '';
        return link;
      },
      { timeout: 20_000 },
    )
    .not.toBe('');
  const url = new URL(link);
  await page.goto(`${url.pathname}${url.search}`);
  await expect(page.getByRole('heading', { name: 'Potvrda pretplate' })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('potvrđena');

  // run the daily job (as cron does) against the dev database
  const sendAlerts = async () => {
    const { execSync } = await import('node:child_process');
    const { readFileSync } = await import('node:fs');
    const root = new URL('../../../../', import.meta.url);
    const dbUrl =
      /^DATABASE_URL=(.*)$/m.exec(readFileSync(new URL('.env', root), 'utf8'))?.[1]?.trim() ?? '';
    execSync('uv run --package nabavaradar-api python -X utf8 -m nabavaradar_api.cli alerts send', {
      cwd: root.pathname.replace(/^\/([A-Za-z]:)/, '$1'),
      env: {
        ...process.env,
        DATABASE_URL: dbUrl.replace(/\/blizu$/, '/nabavaradar'),
        DATA_DIR: 'apps/nabavaradar/data',
      },
      stdio: 'pipe',
      timeout: 180_000,
    });
  };
  await sendAlerts();
  let alertId = '';
  await expect
    .poll(
      async () => {
        alertId = (await mails(`to:${email} subject:"iznad vašeg praga"`))[0]?.ID ?? '';
        return alertId;
      },
      { timeout: 30_000 },
    )
    .not.toBe('');
  const body = await text(alertId);
  expect(body).toMatch(/\/natjecaj\/\d+-\d{4}/);
  expect(body).toContain('Opis nabave sličan je vašoj djelatnosti');
  expect(body).toContain('/pretplata/odjava?token=');
  const settingsLink = body.match(/https?:\/\/\S+pretplata\/postavke\?token=\S+/)?.[0] ?? '';
  expect(settingsLink).not.toBe('');

  // A second run never repeats a notice. (An e-mail holds at most 20 notices; when more qualify, the next run
  // sends the following ones, so a second e-mail is correct as long as no notice appears twice.)
  await sendAlerts();
  const pubsOf = (t: string) =>
    [...t.matchAll(/\/natjecaj\/(\d+-\d{4})/g)].map((m) => m[1] as string);
  const all = await mails(`to:${email} subject:"iznad vašeg praga"`);
  const seen: string[] = [];
  for (const m of all) seen.push(...new Set(pubsOf(await text(m.ID))));
  expect(seen.length).toBeGreaterThan(0);
  expect(new Set(seen).size).toBe(seen.length);

  // the settings link works and can pause the alerts
  const s = new URL(settingsLink);
  await page.goto(`${s.pathname}${s.search}`);
  await expect(page.getByRole('heading', { name: 'Postavke upozorenja' })).toBeVisible();
  await expect(page.getByText(/obavijesti su uključene/)).toBeVisible();
  await page.getByRole('button', { name: 'Pauziraj obavijesti' }).click();
  await expect(page.getByText(/obavijesti su pauzirane/)).toBeVisible();
});

test('banknote: it floats in, a click adds 1 € to a small counter that is remembered', async ({
  page,
}) => {
  await page.goto('/');
  const bill = page.getByRole('button', { name: 'Uhvati novčanicu' });
  await expect(bill).toBeVisible({ timeout: 15_000 });
  const counter = page.getByTestId('bill-counter');
  await expect(counter).toHaveText('Ulovljeno: 0 €');
  // the bill is drifting: Playwright cannot wait for a "stable" element, so dispatch the click
  await bill.dispatchEvent('click');
  await expect(counter).toHaveText('Ulovljeno: 1 €');
  await expect(page.getByText('+1 €').first()).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('bill-counter')).toHaveText('Ulovljeno: 1 €');
  await page.getByRole('button', { name: 'Sakrij novčanicu' }).click();
  await expect(page.getByRole('button', { name: 'Uhvati novčanicu' })).toHaveCount(0);
});

test('banknote under reduced motion: it rests in a corner, keyboard works, none on subscription pages', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const bill = page.getByRole('button', { name: 'Uhvati novčanicu' });
  await expect(bill).toBeVisible();
  await expect(bill).toHaveClass(/nb-bill--still/);
  await bill.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('bill-counter')).toHaveText('Ulovljeno: 1 €');
  await page.goto('/pretplata/odjava?token=x');
  await expect(page.getByRole('button', { name: 'Uhvati novčanicu' })).toHaveCount(0);
});
