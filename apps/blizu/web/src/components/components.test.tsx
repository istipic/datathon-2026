import type { SourcesResponse } from '@dt/ui';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import accessStarija from '../__fixtures__/2026-11-03_access_avdubrovnik_starija.json';
import accessTrg from '../__fixtures__/2026-11-03_access_trg_opce.json';
import geocode from '../__fixtures__/2026-11-03_geocode_ilica200.json';
import sources from '../__fixtures__/2026-11-03_sources_all.json';
import type { AccessResult, GeocodeItem } from '../lib/types';
import { AccessCard } from './AccessCard';
import { AddressSearch, DEBOUNCE_MS, resultLabel } from './AddressSearch';
import { CategoryRow } from './CategoryRow';
import { GradeBadge } from './GradeBadge';
import { LazyMount } from './LazyMount';
import { PersonaControl } from './PersonaControl';

// Fixtures are REAL Blizu API responses recorded on 2026-11-03.
const trg = accessTrg as unknown as AccessResult;
const dubrovnik = accessStarija as unknown as AccessResult;
const allSources = sources as unknown as SourcesResponse;

function withClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('GradeBadge', () => {
  it('always shows the letter and an accessible name', () => {
    render(<GradeBadge grade="C" />);
    const badge = screen.getByRole('img', { name: 'Ocjena C' });
    expect(badge.getAttribute('data-grade')).toBe('C');
    expect(badge.textContent).toBe('C');
    expect(badge.getAttribute('style')).toContain('rgb(154, 125, 10)'); // #9A7D0A
  });

  it('handles a missing grade', () => {
    render(<GradeBadge grade={null} />);
    expect(screen.getByRole('img', { name: 'Ocjena nije dostupna' })).toBeTruthy();
  });
});

describe('PersonaControl', () => {
  it('is a radio group with the active persona checked and focusable only', () => {
    render(<PersonaControl value="roditelj" onChange={() => undefined} />);
    expect(screen.getByRole('radiogroup', { name: 'Za koga računamo' })).toBeTruthy();
    const radios = screen.getAllByRole('radio');
    expect(radios.map((r) => r.getAttribute('aria-checked'))).toEqual([
      'false',
      'false',
      'true',
      'false',
    ]);
    expect(radios.map((r) => r.getAttribute('tabindex'))).toEqual(['-1', '-1', '0', '-1']);
  });

  it('supports arrow keys, Home and End with wrap-around', () => {
    const onChange = vi.fn();
    render(<PersonaControl value="opce" onChange={onChange} />);
    const first = screen.getByRole('radio', { name: /Opće/ });
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    expect(onChange).toHaveBeenLastCalledWith('starija');
    fireEvent.keyDown(first, { key: 'ArrowLeft' });
    expect(onChange).toHaveBeenLastCalledWith('kolica'); // wraps
    fireEvent.keyDown(first, { key: 'End' });
    expect(onChange).toHaveBeenLastCalledWith('kolica');
    fireEvent.keyDown(first, { key: 'Home' });
    expect(onChange).toHaveBeenLastCalledWith('opce');
    onChange.mockClear();
    fireEvent.keyDown(first, { key: 'a' });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('changes persona on click', () => {
    const onChange = vi.fn();
    render(<PersonaControl value="opce" onChange={onChange} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Invalidska kolica' }));
    expect(onChange).toHaveBeenCalledWith('kolica');
  });
});

describe('CategoryRow', () => {
  const ljekarna = trg.categories.find((c) => c.category === 'ljekarna')!;
  const source = allSources.sources.find((s) => s.id === ljekarna.nearest!.source_id);

  it('shows label, minutes in the mono column, nearest facility and score', () => {
    render(
      <ul>
        <CategoryRow result={ljekarna} source={source} onSelect={() => undefined} />
      </ul>,
    );
    expect(screen.getByText('Ljekarna')).toBeTruthy();
    expect(screen.getByTestId('minutes-ljekarna').textContent).toBe('1 min');
    expect(screen.getByTestId('minutes-ljekarna').className).toContain('dt-num');
    expect(screen.getByText(/Ljekarna Centar/)).toBeTruthy();
    expect(screen.getByText(/Ocjena 100 %/)).toBeTruthy();
  });

  it('the accessible name contains the visible text (WCAG 2.5.3)', () => {
    render(
      <ul>
        <CategoryRow result={ljekarna} source={source} onSelect={() => undefined} />
      </ul>,
    );
    const button = screen.getByRole('button', { name: /Ljekarna.*1 min/ });
    expect(button.getAttribute('aria-label')).toBeNull();
    expect(button.textContent).toContain('Prikaži na karti');
  });

  it('selects the category on click and reveals the source on demand', () => {
    const onSelect = vi.fn();
    render(
      <ul>
        <CategoryRow result={ljekarna} source={source} onSelect={onSelect} />
      </ul>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Ljekarna.*1 min/ }));
    expect(onSelect).toHaveBeenCalledWith(ljekarna);
    const toggle = screen.getByRole('button', { name: 'Izvor podataka: Ljekarna' });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const panel = screen.getByTestId('source-ljekarna');
    expect(panel.className).toContain('block');
    expect(panel.textContent).toContain('OpenStreetMap contributors');
    expect(
      within(panel)
        .getByRole('link', { name: /OpenStreetMap/ })
        .getAttribute('href'),
    ).toContain('openstreetmap.org');
    expect(panel.textContent).toContain('Dohvaćeno');
    expect(panel.textContent).toContain('zajednica');
  });

  it('marks categories that do not count for the persona', () => {
    const vrtic = dubrovnik.categories.find((c) => c.category === 'vrtic')!;
    expect(vrtic.weight).toBe(0); // "starija": kindergarten is not relevant
    render(
      <ul>
        <CategoryRow result={vrtic} source={undefined} onSelect={() => undefined} />
      </ul>,
    );
    expect(screen.getByText(/ne ulazi u indeks za ovu osobu/)).toBeTruthy();
    expect(screen.getByText('Izvor nije poznat.')).toBeTruthy();
  });

  it('is honest when there is no data or nothing within reach', () => {
    const none = { ...ljekarna, has_data: false, minutes: null, nearest: null };
    const far = { ...ljekarna, minutes: null, nearest: null };
    const { rerender } = render(
      <ul>
        <CategoryRow result={none} source={undefined} onSelect={() => undefined} />
      </ul>,
    );
    expect(screen.getByTestId('minutes-ljekarna').textContent).toBe('nema podataka');
    rerender(
      <ul>
        <CategoryRow result={far} source={undefined} onSelect={() => undefined} />
      </ul>,
    );
    expect(screen.getByTestId('minutes-ljekarna').textContent).toBe('> 50 min');
    expect(screen.getByText(/Nema objekta u dometu/)).toBeTruthy();
  });
});

describe('AccessCard (real response for Trg bana Jelačića)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(sources)),
    );
  });

  it('renders grade, index, confidence, warnings, 9 rows and the data note', async () => {
    withClient(
      <AccessCard
        title="Trg bana Jelačića"
        result={trg}
        persona="opce"
        onPersona={() => undefined}
      />,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'Trg bana Jelačića' })).toBeTruthy();
    expect(screen.getByRole('img', { name: 'Ocjena A' })).toBeTruthy();
    expect(screen.getByTestId('index').textContent).toContain('100');
    expect(screen.getByText(/Pouzdanost: srednja/)).toBeTruthy();
    expect(
      screen.getAllByRole('listitem').filter((li) => li.hasAttribute('data-category')),
    ).toHaveLength(9);
    expect(screen.getByRole('status').textContent).toContain(
      'Dječji vrtić: podaci su stari 4,4 godina',
    );
    expect(screen.getByRole('radiogroup')).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('data-note').textContent).toContain('dohvaćeno'));
    const note = screen.getByTestId('data-note').textContent!;
    expect(note).toContain('© OpenStreetMap contributors');
    expect(note).toContain('Zagrebački električni tramvaj');
    expect(note).toContain('Grad Zagreb');
  });

  it('shows the starija persona result without the kindergarten/school in the index', () => {
    withClient(<AccessCard title="Avenija Dubrovnik 15" result={dubrovnik} persona="starija" />);
    expect(screen.getByRole('img', { name: `Ocjena ${dubrovnik.grade}` })).toBeTruthy();
    expect(screen.queryByRole('radiogroup')).toBeNull(); // no switcher without onPersona
    expect(screen.getAllByText(/ne ulazi u indeks/)).toHaveLength(2); // vrtic and skola
  });
});

describe('AddressSearch', () => {
  function stubGeocode(response: () => Response | Promise<Response>) {
    const fetchMock = vi.fn<(url: string) => Promise<Response>>(async () => response());
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
  }
  const type = (text: string) =>
    fireEvent.change(screen.getByRole('combobox', { name: 'Adresa u Zagrebu' }), {
      target: { value: text },
    });

  it('debounces by 400 ms, ignores short input and lists real results', async () => {
    expect(DEBOUNCE_MS).toBe(400);
    const fetchMock = stubGeocode(() => json(geocode));
    withClient(<AddressSearch onSelect={() => undefined} />);
    type('Il');
    await act(() => new Promise((r) => setTimeout(r, 600)));
    expect(fetchMock).not.toHaveBeenCalled(); // below 3 characters
    type('Ilica 2');
    type('Ilica 200');
    await act(() => new Promise((r) => setTimeout(r, 250)));
    expect(fetchMock).not.toHaveBeenCalled(); // still inside the debounce window
    const option = await screen.findByRole('option', { name: /Ilica 200/ });
    expect(fetchMock).toHaveBeenCalledTimes(1); // one request for the final text
    expect(String(fetchMock.mock.calls[0]![0])).toBe('/api/v1/geocode?q=Ilica+200');
    expect(option).toBeTruthy();
    expect(screen.getByText('© OpenStreetMap contributors (Nominatim)')).toBeTruthy();
  });

  it('selects with the keyboard (ArrowDown + Enter) and fills the input', async () => {
    stubGeocode(() => json(geocode));
    const onSelect = vi.fn();
    withClient(<AddressSearch onSelect={onSelect} />);
    type('Ilica 200');
    await screen.findByRole('option');
    const input = screen.getByRole('combobox');
    expect(input.getAttribute('aria-expanded')).toBe('true');
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input.getAttribute('aria-activedescendant')).toBeTruthy();
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledTimes(1);
    const picked = onSelect.mock.calls[0]![0] as GeocodeItem;
    expect(picked.title).toBe('Ilica 200');
    expect(picked.lat).toBeCloseTo(45.8125641, 5);
    expect((input as HTMLInputElement).value).toBe(resultLabel(picked));
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('closes the list on Escape', async () => {
    stubGeocode(() => json(geocode));
    withClient(<AddressSearch onSelect={() => undefined} />);
    type('Ilica 200');
    await screen.findByRole('option');
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('shows an empty state when nothing is found', async () => {
    stubGeocode(() =>
      json({
        results: [],
        attribution: 'x',
        fetched_at: '2026-11-03T00:00:00Z',
        from_cache: false,
      }),
    );
    withClient(<AddressSearch onSelect={() => undefined} />);
    type('Nepostojeća ulica 999');
    expect(
      await screen.findByRole('heading', { name: 'Nema rezultata' }, { timeout: 3000 }),
    ).toBeTruthy();
  });

  it('shows an error with retry when the API fails', async () => {
    let calls = 0;
    stubGeocode(() => {
      calls += 1;
      return calls === 1
        ? json(
            { title: 'Bad Gateway', detail: 'Usluga za pretragu adresa trenutno nije dostupna.' },
            502,
          )
        : json(geocode);
    });
    withClient(<AddressSearch onSelect={() => undefined} />);
    type('Ilica 200');
    expect((await screen.findByRole('alert', {}, { timeout: 3000 })).textContent).toContain(
      'trenutno nije dostupna',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Pokušaj ponovno' }));
    expect(await screen.findByRole('option')).toBeTruthy();
  });
});

describe('LazyMount', () => {
  it('mounts children only once the placeholder nears the viewport', () => {
    let trigger: (entries: { isIntersecting: boolean }[]) => void = () => undefined;
    const disconnect = vi.fn();
    class FakeObserver {
      constructor(cb: (entries: { isIntersecting: boolean }[]) => void) {
        trigger = cb;
      }
      observe() {}
      disconnect = disconnect;
    }
    vi.stubGlobal('IntersectionObserver', FakeObserver);
    render(
      <LazyMount placeholder={<span>čekam</span>}>
        <span>karta</span>
      </LazyMount>,
    );
    expect(screen.getByText('čekam')).toBeTruthy();
    expect(screen.queryByText('karta')).toBeNull();
    act(() => trigger([{ isIntersecting: false }]));
    expect(screen.queryByText('karta')).toBeNull();
    act(() => trigger([{ isIntersecting: true }]));
    expect(screen.getByText('karta')).toBeTruthy();
    expect(disconnect).toHaveBeenCalled();
  });

  it('mounts immediately without IntersectionObserver support', () => {
    vi.stubGlobal('IntersectionObserver', undefined);
    render(
      <LazyMount placeholder={<span>čekam</span>}>
        <span>karta</span>
      </LazyMount>,
    );
    expect(screen.getByText('karta')).toBeTruthy();
  });
});
