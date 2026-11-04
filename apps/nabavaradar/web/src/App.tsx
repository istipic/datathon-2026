import { LoadingSkeleton, SkipLink } from '@dt/ui';
import { Suspense, lazy, useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AlertDialogProvider, useAlertDialog } from './components/AlertDialog';
import { BillCounter, Banknote } from './components/Banknote';
import { isQuietRoute } from './lib/banknote';

const page = <T extends string>(load: () => Promise<Record<T, React.ComponentType>>, name: T) =>
  lazy(() => load().then((m) => ({ default: m[name] })));
const HomePage = page(() => import('./pages/HomePage'), 'HomePage');
const CompanyPage = page(() => import('./pages/CompanyPage'), 'CompanyPage');
const NoticePage = page(() => import('./pages/NoticePage'), 'NoticePage');
const BuyerPage = page(() => import('./pages/BuyerPage'), 'BuyerPage');
const AlertsPage = page(() => import('./pages/AlertsPage'), 'AlertsPage');
const SavedPage = page(() => import('./pages/SavedPage'), 'SavedPage');
const SettingsPage = page(() => import('./pages/SettingsPage'), 'SettingsPage');
const SourcesPage = page(() => import('./pages/SourcesPage'), 'SourcesPage');
const ConfirmPage = page(() => import('./pages/ConfirmPage'), 'ConfirmPage');
const UnsubscribePage = page(() => import('./pages/UnsubscribePage'), 'UnsubscribePage');
const NotFoundPage = page(() => import('./pages/NotFoundPage'), 'NotFoundPage');

const NAV = [
  { label: 'Za tvrtke', href: '/' },
  { label: 'Za naručitelje', href: '/narucitelj' },
  { label: 'Upozorenja', href: '/upozorenja' },
  { label: 'Spremljeno', href: '/spremljeno' },
  { label: 'Izvori podataka', href: '/izvori' },
];

function isCurrent(href: string, pathname: string): boolean {
  if (href === '/') {
    return pathname === '/' || pathname.startsWith('/tvrtka') || pathname.startsWith('/natjecaj');
  }
  return pathname.startsWith(href);
}

function Header() {
  const { pathname } = useLocation();
  const { open } = useAlertDialog();
  const [menu, setMenu] = useState(false);
  useEffect(() => setMenu(false), [pathname]);
  return (
    <header className="nb-nav">
      <div className="nb-nav__inner">
        <Link to="/" className="nb-logo">
          <span className="nb-logo__mark" aria-hidden="true">
            B
          </span>
          Birokratko
        </Link>
        <nav className="nb-links" aria-label="Glavna navigacija">
          {NAV.map((item) => (
            <Link
              key={item.href}
              to={item.href}
              aria-current={isCurrent(item.href, pathname) ? 'page' : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <button type="button" className="nb-btn nb-btn--sm nb-cta" onClick={() => open()}>
          Pošalji mi relevantne natječaje
        </button>
        <button
          type="button"
          className="nb-btn nb-btn--light nb-btn--sm nb-burger"
          aria-expanded={menu}
          aria-controls="mobile-menu"
          onClick={() => setMenu((v) => !v)}
        >
          {menu ? 'Zatvori' : 'Izbornik'}
        </button>
      </div>
      {menu ? (
        <nav id="mobile-menu" className="nb-mobile" aria-label="Mobilna navigacija">
          {NAV.map((item) => (
            <Link
              key={item.href}
              to={item.href}
              aria-current={isCurrent(item.href, pathname) ? 'page' : undefined}
            >
              {item.label}
            </Link>
          ))}
          <button type="button" className="nb-btn nb-btn--sm" onClick={() => open()}>
            Pošalji mi relevantne natječaje
          </button>
        </nav>
      ) : null}
    </header>
  );
}

function Footer() {
  const { pathname } = useLocation();
  return (
    <footer className="nb-foot nb-on-dark">
      <div className="nb-wrap grid gap-8 py-10 text-sm md:grid-cols-4">
        <div>
          <p className="nb-label text-lg">Birokratko</p>
          <p className="mt-2">
            Otvoreni javni natječaji koji odgovaraju djelatnosti vaše tvrtke. Prototip za Datathon
            Portala otvorenih podataka 2026.
          </p>
        </div>
        <nav aria-label="Proizvod">
          <p className="nb-label">Proizvod</p>
          <ul className="mt-2 grid gap-1">
            <li>
              <Link to="/">Za tvrtke</Link>
            </li>
            <li>
              <Link to="/narucitelj">Za naručitelje</Link>
            </li>
            <li>
              <Link to="/upozorenja">Upozorenja e-poštom</Link>
            </li>
            <li>
              <Link to="/spremljeno">Spremljeni natječaji</Link>
            </li>
          </ul>
        </nav>
        <nav aria-label="Podaci i izvori">
          <p className="nb-label">Podaci i izvori</p>
          <ul className="mt-2 grid gap-1">
            <li>
              <Link to="/izvori">Izvori podataka i provjera kvalitete</Link>
            </li>
            <li>
              <a href="https://ted.europa.eu" rel="noopener noreferrer">
                TED – Tenders Electronic Daily
              </a>
            </li>
            <li>
              <a href="https://sudreg-data.gov.hr" rel="noopener noreferrer">
                Sudski registar
              </a>
            </li>
          </ul>
        </nav>
        <div>
          <p className="nb-label">Pravno i privatnost</p>
          <p className="mt-2">
            Pohranjujemo samo e-adresu, OIB ili opis pretrage i postavke upozorenja. Odjava je
            jednim klikom u svakoj poruci.
          </p>
          <p className="mt-2">
            <a href="https://spdx.org/licenses/EUPL-1.2.html" rel="noopener noreferrer">
              Izvorni kôd: EUPL-1.2
            </a>
          </p>
          <div className="mt-3 flex gap-2" aria-label="Poveznice">
            <a
              className="nb-square"
              href="https://ted.europa.eu"
              rel="noopener noreferrer"
              aria-label="TED – Tenders Electronic Daily"
            >
              TED
            </a>
            <a
              className="nb-square"
              href="https://sudreg-data.gov.hr"
              rel="noopener noreferrer"
              aria-label="SR – Sudski registar"
            >
              SR
            </a>
            <a
              className="nb-square"
              href="https://spdx.org/licenses/EUPL-1.2.html"
              rel="noopener noreferrer"
              aria-label="EUPL – licenca izvornog koda"
            >
              EUPL
            </a>
          </div>
          {isQuietRoute(pathname) ? null : (
            <div className="mt-4">
              <BillCounter />
            </div>
          )}
        </div>
      </div>
    </footer>
  );
}

export function App() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.documentElement.lang = 'hr';
  }, []);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <AlertDialogProvider>
      <div className="flex min-h-screen flex-col">
        <SkipLink />
        <Header />
        <main id="main" tabIndex={-1} className="flex-1">
          <Suspense
            fallback={
              <div className="mx-auto max-w-5xl p-4">
                <LoadingSkeleton lines={4} label="Učitavam stranicu…" />
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/tvrtka/:oib" element={<CompanyPage />} />
              <Route path="/natjecaj/:pubNo" element={<NoticePage />} />
              <Route path="/narucitelj" element={<BuyerPage />} />
              <Route path="/upozorenja" element={<AlertsPage />} />
              <Route path="/spremljeno" element={<SavedPage />} />
              <Route path="/izvori" element={<SourcesPage />} />
              <Route path="/metodologija" element={<Navigate to="/izvori" replace />} />
              <Route path="/pretplata/potvrda" element={<ConfirmPage />} />
              <Route path="/pretplata/odjava" element={<UnsubscribePage />} />
              <Route path="/pretplata/postavke" element={<SettingsPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </main>
        <Footer />
        <Banknote />
      </div>
    </AlertDialogProvider>
  );
}
