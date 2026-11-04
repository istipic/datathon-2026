import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import consent from '../__fixtures__/2026-11-05_consent_daily_75.json';
import grouped from '../__fixtures__/2026-11-05_match_koncar_grouped.json';
import preview from '../__fixtures__/2026-11-05_alert_preview.json';
import highlights from '../__fixtures__/2026-11-05_highlights.json';
import counties from '../__fixtures__/2026-11-04_counties.json';
import { COUNT_KEY, HIDE_KEY } from '../lib/banknote';
import type { MatchItem } from '../lib/types';
import { AlertDialogProvider, useAlertDialog } from './AlertDialog';
import { AlertForm } from './AlertForm';
import { BillCounter, Banknote } from './Banknote';
import { TenderCard } from './TenderCard';

// Fixtures are REAL API responses recorded on 2026-11-05 (and the counties list of 2026-11-04).
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const items = grouped as unknown as MatchItem[];
const OIB = '45050126417';

function wrap(ui: React.ReactElement, path = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AlertDialogProvider>
          <Routes>
            <Route path="*" element={ui} />
          </Routes>
        </AlertDialogProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function stubMatchMedia(reduced: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: reduced && query.includes('reduce'),
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    })),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.localStorage.clear();
});

describe('AlertForm', () => {
  let bodies: unknown[];
  beforeEach(() => {
    bodies = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.includes('/subscriptions/consent')) return json(consent);
        if (url.includes('/subscriptions/preview')) return json(preview);
        if (url.includes('/highlights')) return json(highlights);
        if (url.includes('/counties')) return json(counties);
        if (url.endsWith('/subscriptions') && init?.method === 'POST') {
          bodies.push(JSON.parse(String(init.body)));
          return json(
            { detail: 'Ako je adresa ispravna, poslali smo poruku za potvrdu pretplate.' },
            202,
          );
        }
        return new Response('not found', { status: 404 });
      }),
    );
  });

  it('shows the live preview and the exact consent text from the API', async () => {
    render(wrap(<AlertForm oib={OIB} />));
    expect(
      await screen.findByText(`S ovim postavkama danas bi dobili ${preview.count} natječaja.`),
    ).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('consent-text').textContent).toBe(consent.text));
  });

  it('needs a valid e-mail, a profile and consent, then posts threshold, filters and frequency', async () => {
    render(wrap(<AlertForm oib={OIB} />));
    const submit = screen.getByRole('button', {
      name: 'Pošalji mi relevantne natječaje',
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('E-adresa'), { target: { value: 'ana@example.hr' } });
    expect(submit.disabled).toBe(true); // consent missing
    fireEvent.click(screen.getByRole('checkbox', { name: /Pristajem da Birokratko/ }));
    expect(submit.disabled).toBe(false);
    fireEvent.change(screen.getByLabelText('Prag prilagodbe u postocima'), {
      target: { value: '82' },
    });
    fireEvent.click(screen.getByText('Filteri (neobavezno)'));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Grad Zagreb' }));
    fireEvent.click(screen.getByRole('radio', { name: /Tjedni pregled/ }));
    fireEvent.change(screen.getByLabelText('Najmanja procijenjena vrijednost (EUR)'), {
      target: { value: '100000' },
    });
    fireEvent.click(submit);
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({
      email: 'ana@example.hr',
      oib: OIB,
      consent: true,
      min_fit: 0.82,
      min_value_eur: 100000,
      counties: [21],
      frequency: 'weekly',
    });
    expect(await screen.findByText(/poslali smo poruku za potvrdu/)).toBeTruthy();
  });

  it('rejects an OIB with a wrong check digit and a malformed e-mail', async () => {
    render(wrap(<AlertForm />));
    fireEvent.change(screen.getByLabelText('OIB tvrtke'), { target: { value: '45050126418' } });
    expect(screen.getByText('Kontrolna znamenka OIB-a nije ispravna.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('E-adresa'), { target: { value: 'nije-adresa' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /Pristajem da Birokratko/ }));
    expect(
      (screen.getByRole('button', { name: 'Pošalji mi relevantne natječaje' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});

describe('AlertDialog', () => {
  function Opener() {
    const { open } = useAlertDialog();
    return (
      <button type="button" onClick={() => open({ oib: OIB })}>
        otvori
      </button>
    );
  }
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({}, 404)),
    );
  });
  it('opens as a labelled modal, closes on Escape and returns focus to the opener', async () => {
    render(wrap(<Opener />));
    const opener = screen.getByRole('button', { name: 'otvori' });
    opener.focus();
    fireEvent.click(opener);
    const dialog = await screen.findByRole('dialog', { name: 'Pošalji mi relevantne natječaje' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect((screen.getByLabelText('OIB tvrtke') as HTMLInputElement).value).toBe(OIB); // prefilled
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(opener);
  });
  it('keeps Tab inside the dialog', async () => {
    render(wrap(<Opener />));
    fireEvent.click(screen.getByRole('button', { name: 'otvori' }));
    const dialog = await screen.findByRole('dialog');
    const close = screen.getByRole('button', { name: 'Zatvori' });
    close.focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(dialog.contains(document.activeElement)).toBe(true);
  });
});

describe('Banknote', () => {
  it('drifts in after a few seconds; catching it adds 1 € to the saved counter', async () => {
    stubMatchMedia(false);
    vi.useFakeTimers();
    render(
      wrap(
        <>
          <Banknote />
          <BillCounter />
        </>,
        '/',
      ),
    );
    expect(screen.queryByRole('button', { name: 'Uhvati novčanicu' })).toBeNull();
    await act(async () => {
      vi.advanceTimersByTime(4100);
    });
    const bill = screen.getByRole('button', { name: 'Uhvati novčanicu' });
    expect(bill.className).toContain('nb-bill--drift');
    expect(screen.getByTestId('bill-counter').textContent).toBe('Ulovljeno: 0 €');
    fireEvent.click(bill);
    expect(screen.getByTestId('bill-counter').textContent).toBe('Ulovljeno: 1 €');
    expect(JSON.parse(window.localStorage.getItem(COUNT_KEY) ?? 'null')).toBe(1);
    expect(document.querySelector('.nb-pop')?.textContent).toBe('+1 €');
    await act(async () => {
      vi.advanceTimersByTime(700);
    });
    expect(screen.queryByRole('button', { name: 'Uhvati novčanicu' })).toBeNull(); // it left
    await act(async () => {
      vi.advanceTimersByTime(41_000);
    });
    expect(screen.getByRole('button', { name: 'Uhvati novčanicu' })).toBeTruthy(); // and a new one came
  });

  it('under reduced motion it rests in a corner and a click only changes the counter', () => {
    stubMatchMedia(true);
    render(
      wrap(
        <>
          <Banknote />
          <BillCounter />
        </>,
      ),
    );
    const bill = screen.getByRole('button', { name: 'Uhvati novčanicu' });
    expect(bill.className).toContain('nb-bill--still');
    expect(bill.className).not.toContain('nb-bill--drift');
    fireEvent.click(bill);
    fireEvent.click(bill);
    expect(screen.getByTestId('bill-counter').textContent).toBe('Ulovljeno: 2 €');
    expect(document.querySelector('.nb-pop')).toBeNull();
    expect(screen.getByRole('button', { name: 'Uhvati novčanicu' })).toBeTruthy();
  });

  it('can be hidden for good, and is not shown on subscription pages', () => {
    stubMatchMedia(true);
    render(
      wrap(
        <>
          <Banknote />
          <BillCounter />
        </>,
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Sakrij novčanicu' }));
    expect(screen.queryByRole('button', { name: 'Uhvati novčanicu' })).toBeNull();
    expect(JSON.parse(window.localStorage.getItem(HIDE_KEY) ?? 'null')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Prikaži novčanicu' }));
    expect(screen.getByRole('button', { name: 'Uhvati novčanicu' })).toBeTruthy();
    cleanup();
    render(wrap(<Banknote />, '/pretplata/odjava'));
    expect(screen.queryByRole('button', { name: 'Uhvati novčanicu' })).toBeNull();
  });
});

describe('TenderCard actions', () => {
  const withGroup = items.find((i) => (i.group?.size ?? 1) > 1) as MatchItem;
  const plain = items.find((i) => (i.group?.size ?? 1) === 1) as MatchItem;
  const card = (ui: React.ReactElement) => render(wrap(<ol>{ui}</ol>));

  it('shows how many more publications of the same procedure were collapsed', () => {
    card(<TenderCard item={withGroup} />);
    const n = withGroup.group!.size - 1;
    expect(screen.getByTestId('group-badge').textContent).toContain(`+${n}`);
    expect(screen.getByText(`Ostale objave istog postupka (${n})`)).toBeTruthy();
  });
  it('does not show a group badge for a single notice', () => {
    card(<TenderCard item={plain} />);
    expect(screen.queryByTestId('group-badge')).toBeNull();
  });
  it('save, hide and calendar buttons call back and respect aria-pressed', () => {
    const onSave = vi.fn();
    const onHide = vi.fn();
    card(<TenderCard item={plain} saved={false} onToggleSave={onSave} onHide={onHide} />);
    const save = screen.getByRole('button', { name: /Prati/ });
    expect(save.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(save);
    expect(onSave).toHaveBeenCalledWith(plain);
    fireEvent.click(screen.getByRole('button', { name: 'Ne zanima me' }));
    expect(onHide).toHaveBeenCalledWith(plain);
    expect(screen.getByRole('button', { name: 'Dodaj rok u kalendar' })).toBeTruthy();
  });
  it('shows the deadline badge as text, not only as colour', () => {
    card(<TenderCard item={{ ...plain, days_left: 2.4 }} />);
    const badge = screen.getByText(/Rok za 2 dana/);
    expect(badge.getAttribute('data-urgency')).toBe('urgent');
  });
});
