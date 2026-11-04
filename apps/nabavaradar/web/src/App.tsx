import { LoadingSkeleton, SkipLink } from '@dt/ui';
import { Suspense, lazy, useEffect } from 'react';
import { Link, Route, Routes, useLocation } from 'react-router-dom';

const page = <T extends string>(load: () => Promise<Record<T, React.ComponentType>>, name: T) =>
  lazy(() => load().then((m) => ({ default: m[name] })));
const HomePage = page(() => import('./pages/HomePage'), 'HomePage');
const CompanyPage = page(() => import('./pages/CompanyPage'), 'CompanyPage');
const NoticePage = page(() => import('./pages/NoticePage'), 'NoticePage');
const BuyerPage = page(() => import('./pages/BuyerPage'), 'BuyerPage');
const MethodologyPage = page(() => import('./pages/MethodologyPage'), 'MethodologyPage');
const SourcesPage = page(() => import('./pages/SourcesPage'), 'SourcesPage');
const ConfirmPage = page(() => import('./pages/ConfirmPage'), 'ConfirmPage');
const UnsubscribePage = page(() => import('./pages/UnsubscribePage'), 'UnsubscribePage');
const NotFoundPage = page(() => import('./pages/NotFoundPage'), 'NotFoundPage');

const NAV = [
  { no: '01', label: 'Za tvrtke', href: '/' },
  { no: '02', label: 'Za naručitelje', href: '/narucitelj' },
  { no: '03', label: 'Metodologija', href: '/metodologija' },
  { no: '04', label: 'Izvori podataka', href: '/izvori' },
];

function isCurrent(href: string, pathname: string): boolean {
  if (href === '/') {
    return pathname === '/' || pathname.startsWith('/tvrtka') || pathname.startsWith('/natjecaj');
  }
  return pathname.startsWith(href);
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
    <div className="flex min-h-screen flex-col">
      <SkipLink />
      <div className="bk-strip bk-label" aria-hidden="true">
        <div className="bk-strip__inner">
          <span>Registar javnih natječaja</span>
          <span>Obrazac JN-1 · otvoreni podaci</span>
        </div>
      </div>
      <header className="bk-head">
        <div className="bk-head__inner">
          <Link to="/" className="bk-stamp" aria-label="Birokratko, početna stranica">
            Birokratko
          </Link>
          <nav className="bk-nav" aria-label="Glavna navigacija">
            {NAV.map((item) => (
              <Link
                key={item.href}
                to={item.href}
                aria-current={isCurrent(item.href, pathname) ? 'page' : undefined}
              >
                <small aria-hidden="true">{item.no}</small>
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
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
            <Route path="/metodologija" element={<MethodologyPage />} />
            <Route path="/izvori" element={<SourcesPage />} />
            <Route path="/pretplata/potvrda" element={<ConfirmPage />} />
            <Route path="/pretplata/odjava" element={<UnsubscribePage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </main>
      <footer className="bk-foot">
        <div className="bk-foot__inner">
          <p>
            Podaci: TED, Sudski registar, CPV 2008. Birokratko je prototip nastao za Datathon
            Portala otvorenih podataka 2026.
          </p>
          <p>
            <Link to="/izvori">Izvori podataka</Link> ·{' '}
            <a href="https://spdx.org/licenses/EUPL-1.2.html">Izvorni kôd: EUPL-1.2</a>
          </p>
        </div>
      </footer>
    </div>
  );
}
