import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import counties from '../__fixtures__/2026-11-04_counties.json';
import match from '../__fixtures__/2026-11-04_match_koncar_top5.json';
import sounding from '../__fixtures__/2026-11-04_sounding_cpv45_split.json';
import validation from '../__fixtures__/2026-11-04_validation.json';
import { explain } from '../lib/explain';
import type { CompetitionInfo, MatchItem, SoundingResult, ValidationResult } from '../lib/types';
import { SourcesPage } from '../pages/SourcesPage';
import { CompetitionChip } from './CompetitionChip';
import { CountyMap, type CountyGeo } from './CountyMap';
import { OibForm } from './OibForm';
import { TenderCard } from './TenderCard';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const items = match as unknown as MatchItem[];
const geo = JSON.parse(
  readFileSync(resolve(__dirname, '../../public/data/counties-hr.geojson'), 'utf-8'),
) as CountyGeo;

const inRouter = (ui: React.ReactElement) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter>{ui}</MemoryRouter>
  </QueryClientProvider>
);

describe('TenderCard (real /match response)', () => {
  it('shows fit, title link, buyer, deadline, value and the competition chip', () => {
    const item = items[0] as MatchItem;
    render(
      inRouter(
        <ul>
          <TenderCard item={item} />
        </ul>,
      ),
    );
    const card = screen.getByTestId('tender-card');
    expect(within(card).getByRole('group', { name: /Prilagodba \d+ posto/ })).toBeTruthy();
    const link = within(card).getByRole('link', { name: item.title ?? '' });
    expect(link.getAttribute('href')).toBe(`/natjecaj/${item.pub_no}`);
    expect(card.textContent).toContain(item.pub_no);
    expect(card.textContent).toMatch(/još \d+ (dan|dana)/);
    expect(card.textContent).toContain('n=');
  });

  it('explains S, C, G and T under "Zašto?"', () => {
    const item = items[0] as MatchItem;
    render(
      inRouter(
        <ul>
          <TenderCard item={item} />
        </ul>,
      ),
    );
    const why = screen.getByText('Zašto?').closest('details') as HTMLElement;
    for (const key of ['S', 'C', 'G', 'T']) {
      expect(within(why).getAllByText(new RegExp(`^${key}`)).length).toBeGreaterThan(0);
    }
    expect(why.textContent).toContain(item.best_activity.label);
  });

  it('ranks items by fit, best first', () => {
    const fits = items.map((i) => i.fit);
    expect(fits).toEqual([...fits].sort((a, b) => b - a));
  });
});

describe('explain()', () => {
  const base = items[0] as MatchItem;
  it('describes the crosswalk level and geography', () => {
    expect(
      explain({ ...base, components: { ...base.components, C: 1 }, division_rank: 2 })[1]?.text,
    ).toContain('među 3');
    expect(
      explain({ ...base, components: { ...base.components, C: 0.5 }, division_rank: 7 })[1]?.text,
    ).toContain('među 10');
    expect(
      explain({ ...base, components: { ...base.components, C: 0 }, division_rank: null })[1]?.text,
    ).toContain('nije među 10');
    expect(explain({ ...base, components: { ...base.components, G: 1 } })[2]?.text).toContain(
      'istoj županiji',
    );
    expect(explain({ ...base, components: { ...base.components, G: 0.2 } })[2]?.text).toContain(
      'drugoj regiji',
    );
    expect(
      explain({ ...base, nuts3: null, components: { ...base.components, G: 0.5 } })[2]?.text,
    ).toContain('nije poznata');
  });
  it('mentions the penalty below 15 days', () => {
    expect(explain({ ...base, days_left: 9 })[3]?.text).toContain('manje od 15 dana');
    expect(explain({ ...base, days_left: 20 })[3]?.text).not.toContain('manje od 15 dana');
  });
});

describe('CompetitionChip', () => {
  const comp = (over: Partial<CompetitionInfo>): CompetitionInfo => ({
    median_submissions: 2,
    single_bid_share: 0.5,
    n: 12,
    flag: true,
    scope: 'HR05',
    ...over,
  });
  it('shows "Niska konkurencija" with n when flagged', () => {
    render(<CompetitionChip competition={comp({})} />);
    expect(screen.getByText(/Niska konkurencija/)).toBeTruthy();
    expect(document.body.textContent).toContain('n=12');
  });
  it('shows n but no warning when not flagged', () => {
    render(<CompetitionChip competition={comp({ flag: false, n: 436 })} />);
    expect(document.body.textContent).not.toContain('Niska konkurencija');
    expect(document.body.textContent).toContain('n=436');
  });
  it('says so when there is no data', () => {
    render(
      <CompetitionChip
        competition={comp({
          n: 0,
          median_submissions: null,
          single_bid_share: null,
          flag: false,
          scope: null,
        })}
      />,
    );
    expect(document.body.textContent).toContain('nema podataka');
  });
});

describe('CountyMap (real polygons and real supplier counts)', () => {
  it('draws all 21 counties with their counts as accessible titles', () => {
    const r = sounding as unknown as SoundingResult;
    const values = Object.fromEntries(r.suppliers_by_county.map((c) => [c.nuts3, c.count]));
    const { container } = render(
      <CountyMap geo={geo} values={values} unit="dobavljača" label="Karta" />,
    );
    const paths = container.querySelectorAll('path[data-nuts3]');
    expect(paths.length).toBe(21);
    expect(container.querySelector('svg')?.getAttribute('role')).toBe('img');
    const zagreb = container.querySelector('path[data-nuts3="HR050"] title');
    const expected = r.suppliers_by_county.find((c) => c.nuts3 === 'HR050')?.count;
    expect(zagreb?.textContent).toBe(`Grad Zagreb: ${expected} dobavljača`);
    // darkest class goes to the county with the most suppliers
    const fills = new Map(
      [...paths].map((p) => [p.getAttribute('data-nuts3'), p.getAttribute('fill')]),
    );
    expect(fills.get('HR050')).toBe('#312E81');
    expect(container.textContent).toContain('EuroGeographics');
  });
});

describe('OibForm', () => {
  it('validates inline and enables submit only for a valid OIB', () => {
    const onSubmit = vi.fn();
    render(<OibForm onSubmit={onSubmit} />);
    const input = screen.getByLabelText('OIB vaše tvrtke') as HTMLInputElement;
    const button = screen.getByRole('button', { name: 'Pronađi natječaje' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.change(input, { target: { value: '4505012' } });
    expect(screen.getByRole('status').textContent).toContain('Još 4 znamenki');
    fireEvent.change(input, { target: { value: '45050126418' } });
    expect(screen.getByRole('status').textContent).toContain('Kontrolna znamenka');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(button.disabled).toBe(true);
    fireEvent.change(input, { target: { value: '45050126417' } });
    expect(screen.getByRole('status').textContent).toContain('OIB je ispravan');
    expect(button.disabled).toBe(false);
    fireEvent.submit(input.closest('form') as HTMLFormElement);
    expect(onSubmit).toHaveBeenCalledWith('45050126417');
  });
});

describe('SourcesPage (live validation numbers)', () => {
  it('renders recall of both methods from /validation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async (url: string) =>
          new Response(JSON.stringify(url.includes('/validation') ? validation : { sources: [] }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    );
    render(inRouter(<SourcesPage />));
    const v = validation as unknown as ValidationResult;
    await waitFor(() => expect(screen.getByText('Birokratko (S/C/G/T)')).toBeTruthy());
    const row = screen.getByText('Birokratko (S/C/G/T)').closest('tr') as HTMLElement;
    expect(row.textContent).toContain(
      `${((v.fit['recall@10'] as number) * 100).toFixed(1).replace('.', ',')} %`,
    );
    expect(screen.getByText('Osnovna: pretraživanje teksta').closest('tr')?.textContent).toContain(
      `${((v.fts_baseline['recall@20'] as number) * 100).toFixed(1).replace('.', ',')} %`,
    );
    expect(document.body.textContent).toContain(v.n.toLocaleString('hr-HR'));
  });
});

describe('counties fixture', () => {
  it('has the 21 counties with NUTS codes', () => {
    expect(counties.length).toBe(21);
    expect(counties.find((c) => c.code === 21)?.nuts3).toBe('HR050');
  });
});
