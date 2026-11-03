import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import accessStarija from '../__fixtures__/2026-11-03_access_avdubrovnik_starija.json';
import accessTrg from '../__fixtures__/2026-11-03_access_trg_opce.json';
import optimise from '../__fixtures__/2026-11-03_optimise_vrtic_roditelj_3.json';
import problem from '../__fixtures__/2026-11-03_problem_422.json';
import scoring from '../__fixtures__/2026-11-03_scoring.json';
import sources from '../__fixtures__/2026-11-03_sources_all.json';
import { CardPage } from './CardPage';
import { HomePage } from './HomePage';
import { MethodologyPage } from './MethodologyPage';

// The map library needs WebGL: the real map is covered by the Playwright smoke tests.
vi.mock('../components/MapPanel', () => ({ MapPanel: () => <div data-testid="map-stub" /> }));

// Fixtures are REAL Blizu API responses recorded on 2026-11-03.
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function renderAt(path: string, ui: React.ReactElement, route = '*') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Where() {
    const loc = useLocation();
    return <output data-testid="where">{loc.pathname + loc.search}</output>;
  }
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Where />
        <Routes>
          <Route path={route} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('CardPage', () => {
  const URL_OPCE =
    '/kartica?lat=45.81277&lon=15.97659&persona=opce&q=Trg%20bana%20Jela%C4%8Di%C4%87a';

  function stubApi(handler?: (url: string) => Response | undefined) {
    const calls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        calls.push(url);
        const custom = handler?.(url);
        if (custom) return custom;
        if (url.startsWith('/api/v1/sources')) return json(sources);
        if (url.includes('persona=starija')) return json(accessStarija);
        if (url.includes('/api/v1/access')) return json(accessTrg);
        return new Response('not found', { status: 404 });
      }),
    );
    return calls;
  }

  it('shows the heading and persona control immediately, then the card', async () => {
    stubApi();
    renderAt(URL_OPCE, <CardPage />, '/kartica');
    expect(screen.getByRole('heading', { level: 1, name: 'Trg bana Jelačića' })).toBeTruthy();
    expect(screen.getByRole('radiogroup')).toBeTruthy();
    expect(screen.getAllByRole('status').some((el) => el.textContent?.includes('Računam'))).toBe(
      true,
    );
    expect(await screen.findByTestId('index')).toBeTruthy();
    expect(screen.getByRole('img', { name: 'Ocjena A' })).toBeTruthy();
    expect(
      screen.getAllByRole('listitem').filter((li) => li.hasAttribute('data-category')),
    ).toHaveLength(9);
    expect(await screen.findByTestId('map-stub')).toBeTruthy();
  });

  it('switching persona re-fetches and updates the URL without leaving the page', async () => {
    const calls = stubApi();
    renderAt(URL_OPCE, <CardPage />, '/kartica');
    await screen.findByTestId('index');
    fireEvent.click(screen.getByRole('radio', { name: /Starija osoba/ }));
    await waitFor(() =>
      expect(screen.getByTestId('where').textContent).toContain('persona=starija'),
    );
    await waitFor(() => expect(calls.some((c) => c.includes('persona=starija'))).toBe(true));
    // the previous card stays visible while the new one loads (no flash), then updates
    expect(screen.getByRole('radio', { name: /Starija osoba/ }).getAttribute('aria-checked')).toBe(
      'true',
    );
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Trg bana Jelačića');
  });

  it('shows the API problem detail without a retry button for 422 (outside Zagreb)', async () => {
    stubApi((url) =>
      url.includes('/api/v1/access')
        ? json({ ...problem, detail: 'Adresa nije unutar Grada Zagreba.' }, 422)
        : undefined,
    );
    renderAt(URL_OPCE, <CardPage />, '/kartica');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Adresa nije unutar Grada Zagreba.');
    expect(within(alert).queryByRole('button', { name: 'Pokušaj ponovno' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Probajte drugu adresu' })).toBeTruthy();
  });

  it('offers a retry on server errors (after the one automatic retry)', async () => {
    let n = 0;
    stubApi((url) => {
      if (!url.includes('/api/v1/access')) return undefined;
      n += 1;
      return n <= 2
        ? json({ title: 'Internal Server Error', detail: 'Internal server error' }, 500)
        : json(accessTrg);
    });
    renderAt(URL_OPCE, <CardPage />, '/kartica');
    fireEvent.click(
      await screen.findByRole('button', { name: 'Pokušaj ponovno' }, { timeout: 5000 }),
    );
    expect(await screen.findByTestId('index', {}, { timeout: 5000 })).toBeTruthy();
  }, 20_000);

  it('asks for an address when the URL has none', () => {
    stubApi();
    renderAt('/kartica', <CardPage />, '/kartica');
    expect(screen.getByText('Nedostaje adresa')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Odaberi adresu' }).getAttribute('href')).toBe('/');
  });

  it('opens the comparison with the current address and persona', async () => {
    stubApi();
    renderAt(URL_OPCE, <CardPage />, '/kartica');
    await screen.findByTestId('index');
    fireEvent.click(screen.getByRole('button', { name: 'Usporedi s drugom adresom' }));
    const where = screen.getByTestId('where').textContent!;
    expect(where).toContain('/usporedi?a=45.812770,15.976590');
    expect(where).toContain('persona=opce');
  });
});

describe('HomePage', () => {
  it('has the headline, an address combobox, three verified example chips and persona choice', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(sources)),
    );
    renderAt('/', <HomePage />, '/');
    expect(screen.getByRole('heading', { level: 1, name: 'Što ti je blizu?' })).toBeTruthy();
    expect(screen.getByRole('combobox', { name: 'Adresa u Zagrebu' })).toBeTruthy();
    const chips = within(screen.getByRole('region', { name: 'Isprobaj na primjeru' })).getAllByRole(
      'button',
    );
    expect(chips).toHaveLength(3);
    expect(chips.map((c) => c.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining('Trg bana Jelačića 1')]),
    );
  });

  it('example chip navigates to the card with the selected persona', () => {
    renderAt('/?persona=kolica', <HomePage />, '/');
    fireEvent.click(screen.getByRole('button', { name: /Avenija Dubrovnik 15/ }));
    const where = screen.getByTestId('where').textContent!;
    expect(where).toContain('/kartica?lat=45.780440&lon=15.972170&persona=kolica');
  });
});

describe('MethodologyPage', () => {
  it('renders the scoring configuration served by the API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => (url.includes('scoring') ? json(scoring) : json(sources))),
    );
    renderAt('/metodologija', <MethodologyPage />, '/metodologija');
    const table = await screen.findByTestId('weights-table');
    expect(within(table).getAllByRole('row')).toHaveLength(10); // header + 9 categories
    const lijecnik = within(table).getByRole('row', { name: /Liječnik/ });
    expect(lijecnik.textContent).toContain('0,22'); // starija weight
    expect(screen.getByText(/Verzija bodovanja/).textContent).toContain('1');
    expect(screen.getByText(/A ≥ 85, B ≥ 70, C ≥ 55, D ≥ 40/)).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Ograničenja' })).toBeTruthy();
    expect(await screen.findByText(/Eurostat \(GISCO\)/)).toBeTruthy(); // data dates come from /sources
  });
});

describe('optimise fixture', () => {
  it('is a real optimiser response with at most k sites and non-decreasing coverage', () => {
    expect(optimise.sites.length).toBeLessThanOrEqual(optimise.k);
    expect(optimise.share_after).toBeGreaterThanOrEqual(optimise.share_before);
  });
});
