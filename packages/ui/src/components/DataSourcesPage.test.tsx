import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import problem404 from '../__fixtures__/2026-11-03_problem_404.json';
import sourcesEmpty from '../__fixtures__/2026-11-03_sources_empty.json';
import sourcesLoaded from '../__fixtures__/2026-11-03_sources_eurostat_sample_load.json';
import { DataSourcesPage } from './DataSourcesPage';

// Fixtures are REAL responses recorded from opendata_core's create_app on 2026-11-03
// (the "loaded" one after a real PostGIS load of Eurostat sample rows).

function renderPage(props: Parameters<typeof DataSourcesPage>[0] = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DataSourcesPage {...props} />
    </QueryClientProvider>,
  );
}

function mockFetch(impl: (url: string) => Response | Promise<Response>) {
  const fn = vi.fn((url: string) => Promise.resolve(impl(url)));
  vi.stubGlobal('fetch', fn);
  return fn;
}

const json = (body: unknown, status = 200, contentType = 'application/json') =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': contentType } });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('DataSourcesPage', () => {
  it('fetches /api/v1/sources and shows a loading status first', async () => {
    const fetchMock = mockFetch(() => json(sourcesLoaded));
    renderPage();
    expect(screen.getByRole('status').textContent).toContain('Učitavanje izvora podataka');
    await screen.findByRole('table');
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/sources');
  });

  it('renders one row per source with publisher, licence, retrieval time, freshness and rows', async () => {
    mockFetch(() => json(sourcesLoaded));
    renderPage();
    const table = await screen.findByRole('table');
    expect(
      within(table).getByText('Popis izvora podataka i vrijeme njihova dohvaćanja'),
    ).toBeTruthy();
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(2); // header + 1 source
    const row = rows[1]!;
    const link = within(row).getByRole('link', { name: /Census 2021 population grid/ });
    expect(link.getAttribute('href')).toContain('ec.europa.eu/eurostat');
    expect(within(row).getByText('Eurostat (GISCO)')).toBeTruthy();
    expect(within(row).getByRole('link', { name: /Eurostat copyright policy/ })).toBeTruthy();
    expect(within(row).getByText('Preuzimanje')).toBeTruthy();
    expect(within(row).getByText('Službeni (EU)')).toBeTruthy();
    expect(within(row).getByText(/Starost podataka: 137 dana \(starije\)/)).toBeTruthy();
    expect(within(row).getByText('10')).toBeTruthy();
    expect(row.querySelector('time')?.getAttribute('datetime')).toContain('2026-11-03T19:02:48');
  });

  it('has column headers with scope and wraps results in a polite live region', async () => {
    mockFetch(() => json(sourcesLoaded));
    const { container } = renderPage();
    await screen.findByRole('table');
    expect(screen.getAllByRole('columnheader')).toHaveLength(8);
    expect(container.querySelector('[aria-live="polite"]')).toBeTruthy();
    expect(screen.getByRole('heading', { level: 1, name: 'Izvori podataka' })).toBeTruthy();
  });

  it('shows an empty state when no sources are registered', async () => {
    mockFetch(() => json(sourcesEmpty));
    renderPage();
    expect(await screen.findByText('Još nema učitanih izvora')).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('shows the server problem+json detail and retries on demand', async () => {
    let calls = 0;
    const fetchMock = mockFetch(() => {
      calls += 1;
      return calls === 1
        ? json(
            { ...problem404, status: 503, detail: 'Baza nije dostupna' },
            503,
            'application/problem+json',
          )
        : json(sourcesLoaded);
    });
    renderPage();
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Baza nije dostupna');
    fireEvent.click(screen.getByRole('button', { name: 'Pokušaj ponovno' }));
    await screen.findByRole('table');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('falls back to the title when the problem has no detail, and to a status message for non-JSON', async () => {
    mockFetch(() => json({ title: 'Not Found', status: 404 }, 404, 'application/problem+json'));
    renderPage();
    expect((await screen.findByRole('alert')).textContent).toContain('Not Found');
    cleanup();
    mockFetch(() => new Response('<html>bad gateway</html>', { status: 502 }));
    renderPage();
    expect((await screen.findByRole('alert')).textContent).toContain('status 502');
  });

  it('supports a custom endpoint and title', async () => {
    const fetchMock = mockFetch(() => json(sourcesLoaded));
    renderPage({ endpoint: '/blizu/api/v1/sources', title: 'Odakle podaci' });
    await screen.findByRole('table');
    expect(fetchMock.mock.calls[0]![0]).toBe('/blizu/api/v1/sources');
    expect(screen.getByRole('heading', { name: 'Odakle podaci' })).toBeTruthy();
  });

  it('handles a source that was never loaded (no run, no licence)', async () => {
    const never = {
      sources: [
        {
          id: 'x',
          title: 'Neučitani izvor',
          publisher: 'Izdavač',
          url: 'https://example.org',
          license_name: null,
          license_url: null,
          access_method: 'api',
          tier: 'community',
          notes: null,
          last_run: null,
          retrieved_at: null,
          freshness_days: null,
        },
      ],
      generated_at: '2026-11-03T00:00:00+00:00',
    };
    mockFetch(() => json(never));
    renderPage();
    const table = await screen.findByRole('table');
    await waitFor(() => expect(within(table).getByText('Još nije dohvaćeno')).toBeTruthy());
    expect(within(table).getByText('Nije navedena')).toBeTruthy();
    expect(within(table).getByText('Starost podataka nije poznata')).toBeTruthy();
    expect(within(table).getByText('Zajednica')).toBeTruthy();
    expect(within(table).getByText('–')).toBeTruthy();
  });
});
