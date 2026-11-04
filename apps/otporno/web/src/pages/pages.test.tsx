import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import dhmzLive from '../__fixtures__/2026-11-04_dhmz_live_karlovac.json';
import cooling from '../__fixtures__/2026-11-04_cooling_karlovac_3.json';
import exposure from '../__fixtures__/2026-11-04_exposure_karlovac.json';
import municipalities from '../__fixtures__/2026-11-04_municipalities_karlo.json';
import passport from '../__fixtures__/2026-11-04_passport_karlovac.json';
import problem from '../__fixtures__/2026-11-04_problem_422.json';
import { HeatBars } from '../components/HeatBars';
import { RingGauge } from '../components/RingGauge';
import type { HeatBlock } from '../lib/types';
import { HomePage } from './HomePage';
import { MethodologyPage } from './MethodologyPage';
import { MunicipalitiesPage } from './MunicipalitiesPage';
import { PassportPage } from './PassportPage';

// The map library needs WebGL: the real maps are covered by the Playwright smoke test.
vi.mock('../components/FloodMap', () => ({ FloodMap: () => <div data-testid="flood-map-stub" /> }));
vi.mock('../components/PriorityMap', () => ({
  PriorityMap: () => <div data-testid="priority-map-stub" />,
}));

// Fixtures are REAL Otporko API responses recorded on 2026-11-04.
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function renderAt(path: string, ui: React.ReactElement, route = '*') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// The passport page also asks for the latest DHMZ observation.
const passportApi = async (url: string) =>
  url.includes('/live/dhmz') ? json(dhmzLive) : json(passport);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('RingGauge', () => {
  it('spells the band out and never relies on colour alone', () => {
    render(<RingGauge band="visoka" hazard="Vrućina" />);
    expect(screen.getByRole('img', { name: 'Vrućina: razina visoka' })).toBeInTheDocument();
    expect(screen.getByText('Visoka')).toBeInTheDocument();
    expect(screen.getByText('3/4')).toBeInTheDocument();
  });
  it('says so when the level is unknown', () => {
    render(<RingGauge band={null} hazard="Poplava" unknownLabel="Razina nije određena" />);
    expect(screen.getByText('Razina nije određena')).toBeInTheDocument();
  });
});

describe('HeatBars', () => {
  it('writes out the values and the model range', () => {
    render(<HeatBars heat={passport.heat as unknown as HeatBlock} />);
    expect(screen.getByRole('group', { name: /Vrući dani godišnje/ })).toBeInTheDocument();
    expect(screen.getByText(/Raspon između tri klimatska modela/)).toBeInTheDocument();
    expect(screen.getByText(/17,0 dana/)).toBeInTheDocument();
  });
});

describe('HomePage', () => {
  it('offers the address search and the demo municipalities', () => {
    renderAt('/', <HomePage />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'izložena poplavi i vrućini',
    );
    expect(
      screen.getByRole('combobox', { name: /Adresa bilo gdje u Hrvatskoj/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Grad Karlovac' })).toHaveAttribute(
      'href',
      '/opcina/HR_01791',
    );
    expect(screen.getByRole('link', { name: 'Grad Zagreb' })).toHaveAttribute(
      'href',
      '/opcina/HR_01333',
    );
  });
});

describe('PassportPage', () => {
  const URL = '/putovnica?lat=45.4929&lon=15.5553&q=Karlovac';
  it('shows three hazard cards, cited actions and the flood disclaimer', async () => {
    const fetchMock = vi.fn(passportApi);
    vi.stubGlobal('fetch', fetchMock);
    renderAt(URL, <PassportPage />);
    await screen.findByRole('heading', { level: 2, name: 'Vrućina' });
    expect(screen.getByRole('heading', { level: 2, name: 'Poplava' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Požar' })).toBeInTheDocument();
    expect(screen.getByText(passport.flood.message as string)).toBeInTheDocument();
    expect(screen.getByText(/Oko \d+ % točaka/)).toBeInTheDocument();
    expect(screen.getByText(/Pouzdanost: srednja/)).toBeInTheDocument();
    expect(screen.getByText(/Pokrov zemljišta na adresi/)).toBeInTheDocument();
    expect(screen.getByText(/Discontinuous urban fabric/)).toBeInTheDocument();
    const todo = screen.getByRole('region', { name: 'Što učiniti' });
    const links = within(todo).getAllByRole('link');
    expect(links.length).toBeGreaterThanOrEqual(6);
    for (const a of links) expect(a).toHaveAttribute('href', expect.stringMatching(/^https:\/\//));
    expect(screen.getByTestId('flood-map-stub')).toBeInTheDocument();
    expect(screen.getAllByText(/Hrvatske vode ne jamče/).length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/passport?lat=45.4929&lon=15.5553'),
      expect.anything(),
    );
  });

  it('remembers ticked steps in this browser', async () => {
    vi.stubGlobal('fetch', vi.fn(passportApi));
    renderAt(URL, <PassportPage />);
    await screen.findByRole('heading', { level: 2, name: 'Vrućina' });
    const first = screen.getAllByRole('checkbox')[0] as HTMLInputElement;
    fireEvent.click(first);
    expect(first.checked).toBe(true);
    expect(window.localStorage.getItem('otporko-ticks-45.493-15.555')).toContain(
      first.id.replace('chk-', ''),
    );
  });

  it('shows the nearest DHMZ station, and hides data that is too old', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url.includes('/live/dhmz')
          ? json({
              ...dhmzLive,
              status: 'stale',
              message: 'Podaci DHMZ-a stariji su od 3 sata i zato se ne prikazuju.',
              stations: [],
            })
          : json(passport),
      ),
    );
    renderAt(URL, <PassportPage />);
    expect(await screen.findByText(/stariji su od 3 sata/)).toBeTruthy();
    cleanup();
    vi.stubGlobal('fetch', vi.fn(passportApi));
    renderAt(URL, <PassportPage />);
    expect(await screen.findByText(/km od adrese/)).toBeTruthy();
    expect(screen.getByText(/Karlovac/, { selector: 'strong' })).toBeTruthy();
  });

  it('explains a point outside Croatia (422) without a retry button', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(problem, 422)),
    );
    renderAt('/putovnica?lat=48.8566&lon=2.3522', <PassportPage />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Točka nije unutar Hrvatske');
    expect(within(alert).queryByRole('button')).toBeNull();
  });

  it('shows an error with retry for a server failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ detail: 'Greška poslužitelja' }, 500)),
    );
    renderAt(URL, <PassportPage />);
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByRole('button', { name: 'Pokušaj ponovno' })).toBeInTheDocument();
  });

  it('asks for an address when coordinates are missing', () => {
    renderAt('/putovnica', <PassportPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('Nedostaje adresa');
  });
});

describe('MunicipalitiesPage', () => {
  it('searches municipalities by name', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(municipalities)),
    );
    renderAt('/opcina', <MunicipalitiesPage />);
    fireEvent.change(screen.getByLabelText('Naziv općine ili grada'), {
      target: { value: 'karlo' },
    });
    const link = await screen.findByRole(
      'link',
      { name: /Karlovac.*stanovnika/ },
      { timeout: 3000 },
    );
    expect(link).toHaveAttribute('href', '/opcina/HR_01791');
  });
});

describe('MunicipalityPage', () => {
  it('reconciles the KPI tiles with the exposure numbers', async () => {
    const { MunicipalityPage } = await import('./MunicipalityPage');
    const cells = {
      type: 'FeatureCollection',
      features: [],
      summary: {
        cells: 270,
        pop_total: 49669,
        pop_65p: 12337,
        breaks: [],
        weights: {},
        weights_effective: {},
        lau_id: 'HR_01791',
      },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => (url.includes('/cells') ? json(cells) : json(exposure))),
    );
    renderAt('/opcina/HR_01791', <MunicipalityPage />, '/opcina/:lau');
    await screen.findByRole('heading', { level: 1, name: 'Karlovac' });
    const tiles = screen.getByRole('region', { name: 'Ključni pokazatelji' });
    expect(within(tiles).getByText('49.669')).toBeInTheDocument();
    expect(within(tiles).getByText('12.337')).toBeInTheDocument();
    expect(within(tiles).getByText('nije dostupno')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: /Stanovnici po razini toplinskog rizika/ });
    const rows = within(table).getAllByRole('row');
    expect(rows.length).toBeGreaterThanOrEqual(6);
    expect(screen.getByRole('button', { name: 'Predloži lokacije' })).toBeInTheDocument();
    expect(cooling.sites.length).toBe(3);
  });

  it('offers to start the computation when it was never run', async () => {
    const { MunicipalityPage } = await import('./MunicipalityPage');
    const body = { ...exposure, status: 'unavailable', message: null, can_compute: true };
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(body)),
    );
    renderAt('/opcina/HR_01791', <MunicipalityPage />, '/opcina/:lau');
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Pokreni izračun' })).toBeInTheDocument(),
    );
  });

  it('polls while the computation is running', async () => {
    const { MunicipalityPage } = await import('./MunicipalityPage');
    const body = { ...exposure, status: 'computing' };
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(body)),
    );
    renderAt('/opcina/HR_01791', <MunicipalityPage />, '/opcina/:lau');
    expect(await screen.findByText('Izračun je u tijeku…')).toBeInTheDocument();
    expect(screen.getByText(/svakih 5 sekundi/)).toBeInTheDocument();
  });
});

describe('MethodologyPage', () => {
  it('names the flood ladder step and the disclaimer', () => {
    renderAt('/metodologija', <MethodologyPage />);
    expect(screen.getByText(/samo prikaz karte/)).toBeInTheDocument();
    expect(screen.getByText(/Hrvatske vode ne jamče za posljedice korištenja/)).toBeInTheDocument();
  });
});
