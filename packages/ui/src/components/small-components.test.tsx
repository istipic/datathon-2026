import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { AppShell } from './AppShell';
import { ConfidenceBadge } from './ConfidenceBadge';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { FreshnessChip, freshnessLevel } from './FreshnessChip';
import { LoadingSkeleton } from './LoadingSkeleton';
import { SkipLink } from './SkipLink';
import { SourceBadge } from './SourceBadge';

afterEach(cleanup);

describe('SkipLink', () => {
  it('links to #main by default and is a real link', () => {
    render(<SkipLink />);
    const link = screen.getByRole('link', { name: 'Preskoči na sadržaj' });
    expect(link.getAttribute('href')).toBe('#main');
  });

  it('accepts a custom target and label', () => {
    render(<SkipLink href="#content">Idi na sadržaj</SkipLink>);
    expect(screen.getByRole('link', { name: 'Idi na sadržaj' }).getAttribute('href')).toBe(
      '#content',
    );
  });
});

describe('AppShell', () => {
  const nav = [
    { label: 'Karta', href: '/', current: true },
    { label: 'O projektu', href: '/o-projektu' },
  ];

  it('renders landmarks: skip link, banner, labelled nav, main, contentinfo', () => {
    render(
      <AppShell brandName="Blizu" logo="★" nav={nav}>
        <p>Sadržaj</p>
      </AppShell>,
    );
    expect(screen.getByRole('link', { name: 'Preskoči na sadržaj' })).toBeTruthy();
    expect(screen.getByRole('banner')).toBeTruthy();
    expect(screen.getByRole('navigation', { name: 'Glavna navigacija' })).toBeTruthy();
    const main = screen.getByRole('main');
    expect(main.id).toBe('main');
    expect(main.textContent).toContain('Sadržaj');
    expect(screen.getByRole('contentinfo')).toBeTruthy();
  });

  it('marks the current page with aria-current and hides the decorative logo', () => {
    render(
      <AppShell brandName="Blizu" logo="★" nav={nav}>
        x
      </AppShell>,
    );
    expect(screen.getByRole('link', { name: 'Karta' }).getAttribute('aria-current')).toBe('page');
    expect(
      screen.getByRole('link', { name: 'O projektu' }).getAttribute('aria-current'),
    ).toBeNull();
    // brand link's accessible name is the brand, not the glyph
    expect(screen.getByRole('link', { name: 'Blizu' })).toBeTruthy();
  });

  it('footer has the "Izvori podataka" link and the default licence', () => {
    render(<AppShell brandName="Blizu">x</AppShell>);
    const footer = screen.getByRole('contentinfo');
    const sources = Array.from(footer.querySelectorAll('a')).find(
      (a) => a.textContent === 'Izvori podataka',
    );
    expect(sources?.getAttribute('href')).toBe('/izvori-podataka');
    expect(footer.textContent).toContain('EUPL-1.2');
  });

  it('supports custom sources link, licences and extra footer content', () => {
    render(
      <AppShell
        brandName="Blizu"
        sourcesHref="/izvori"
        licences={[{ label: 'CC BY 4.0', href: 'https://example.org/l' }]}
        footer={<span>Napomena</span>}
      >
        x
      </AppShell>,
    );
    const footer = screen.getByRole('contentinfo');
    expect(footer.querySelector('a[href="/izvori"]')).toBeTruthy();
    const lic = screen.getByRole('link', { name: 'CC BY 4.0' });
    expect(lic.getAttribute('rel')).toBe('noopener noreferrer');
    expect(footer.textContent).toContain('Napomena');
  });

  it('omits the nav landmark when there are no nav items and sets html lang="hr"', () => {
    document.documentElement.lang = 'en';
    render(<AppShell brandName="Blizu">x</AppShell>);
    expect(screen.queryByRole('navigation')).toBeNull();
    expect(document.documentElement.lang).toBe('hr');
  });
});

describe('SourceBadge', () => {
  const props = {
    publisher: 'Eurostat (GISCO)',
    title: 'Census 2021 grid',
    url: 'https://ec.europa.eu/eurostat',
  };

  it('shows publisher, link to the source and the retrieval time', () => {
    render(<SourceBadge {...props} retrievedAt="2026-11-03T18:31:50Z" />);
    const link = screen.getByRole('link', { name: 'Census 2021 grid' });
    expect(link.getAttribute('href')).toBe(props.url);
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    expect(screen.getByText(/Eurostat \(GISCO\)/)).toBeTruthy();
    const time = document.querySelector('time');
    expect(time?.getAttribute('datetime')).toBe('2026-11-03T18:31:50.000Z');
    expect(time?.textContent).toContain('19:31');
  });

  it('says so when the retrieval time is unknown (never silently omitted)', () => {
    render(<SourceBadge {...props} retrievedAt={null} />);
    expect(screen.getByText('Vrijeme dohvaćanja nije poznato')).toBeTruthy();
    expect(document.querySelector('time')).toBeNull();
  });
});

describe('FreshnessChip', () => {
  it.each([
    [0, 'success'],
    [30, 'success'],
    [31, 'warning'],
    [365, 'warning'],
    [366, 'danger'],
    [2000, 'danger'],
    [null, 'neutral'],
    [undefined, 'neutral'],
  ] as const)('%s days → %s', (days, level) => {
    expect(freshnessLevel(days)).toBe(level);
  });

  it('always renders text with the age and a state word (colour is not the only signal)', () => {
    const { container } = render(<FreshnessChip days={12} />);
    expect(container.textContent).toContain('Starost podataka: 12 dana');
    expect(container.textContent).toContain('ažurno');
    expect(container.firstElementChild?.getAttribute('data-level')).toBe('success');
    cleanup();
    const second = render(<FreshnessChip days={1} />);
    expect(second.container.textContent).toContain('1 dan (ažurno)');
    cleanup();
    expect(render(<FreshnessChip days={100} />).container.textContent).toContain('(starije)');
    cleanup();
    expect(render(<FreshnessChip days={400} />).container.textContent).toContain('(zastarjelo)');
  });

  it('handles unknown age with text', () => {
    const { container } = render(<FreshnessChip days={null} />);
    expect(container.textContent).toContain('Starost podataka nije poznata');
    expect(container.firstElementChild?.getAttribute('data-level')).toBe('neutral');
  });

  it('hides decorative glyphs from assistive tech', () => {
    const { container } = render(<FreshnessChip days={400} />);
    expect(container.querySelector('[aria-hidden="true"]')).toBeTruthy();
  });
});

describe('ConfidenceBadge', () => {
  it.each(['visoka', 'srednja', 'niska'] as const)('spells out the level "%s"', (level) => {
    const { container } = render(<ConfidenceBadge level={level} />);
    expect(container.textContent).toContain(`Pouzdanost: ${level}`);
    expect(container.firstElementChild?.getAttribute('data-level')).toBe(level);
    cleanup();
  });

  it('uses different dot patterns per level', () => {
    const dots = (['visoka', 'srednja', 'niska'] as const).map((level) => {
      const { container } = render(<ConfidenceBadge level={level} />);
      const text = container.querySelector('[aria-hidden="true"]')?.textContent;
      cleanup();
      return text;
    });
    expect(new Set(dots).size).toBe(3);
  });
});

describe('LoadingSkeleton', () => {
  it('is a polite, busy status region with screen-reader text', () => {
    render(<LoadingSkeleton />);
    const status = screen.getByRole('status');
    expect(status.getAttribute('aria-live')).toBe('polite');
    expect(status.getAttribute('aria-busy')).toBe('true');
    expect(status.textContent).toContain('Učitavanje…');
    expect(status.querySelectorAll('.dt-skeleton__line').length).toBe(3);
  });

  it('supports a custom number of lines and label', () => {
    render(<LoadingSkeleton lines={5} label="Učitavam kartu" />);
    expect(screen.getByRole('status').querySelectorAll('.dt-skeleton__line').length).toBe(5);
    expect(screen.getByText('Učitavam kartu')).toBeTruthy();
  });
});

describe('EmptyState', () => {
  it('renders title, body and action in a polite live region', () => {
    render(
      <EmptyState
        title="Nema rezultata"
        body="Pokušajte drugi upit."
        action={<button>Očisti</button>}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Nema rezultata' })).toBeTruthy();
    expect(screen.getByText('Pokušajte drugi upit.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Očisti' })).toBeTruthy();
    expect(document.querySelector('[aria-live="polite"]')).toBeTruthy();
  });

  it('works without body and action', () => {
    const { container } = render(<EmptyState title="Prazno" />);
    expect(container.querySelector('p')).toBeNull();
  });
});

describe('ErrorState', () => {
  it('is an alert with the message and no retry button by default', () => {
    render(<ErrorState message="Poslužitelj ne odgovara" />);
    expect(screen.getByRole('alert').textContent).toContain('Poslužitelj ne odgovara');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('calls onRetry when the retry button is clicked', () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Greška" onRetry={onRetry} />);
    fireEvent.click(screen.getByRole('button', { name: 'Pokušaj ponovno' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
