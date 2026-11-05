import { LoadingSkeleton, SkipLink } from '@dt/ui';
import { Suspense, lazy, useEffect } from 'react';
import { Link, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Icon, LogoMark } from './components/ui';

const page = <T extends string>(load: () => Promise<Record<T, React.ComponentType>>, name: T) =>
  lazy(() => load().then((m) => ({ default: m[name] })));
const HomePage = page(() => import('./pages/HomePage'), 'HomePage');
const CardPage = page(() => import('./pages/CardPage'), 'CardPage');
const ComparePage = page(() => import('./pages/ComparePage'), 'ComparePage');
const PlanningPage = page(() => import('./pages/PlanningPage'), 'PlanningPage');
const MethodologyPage = page(() => import('./pages/MethodologyPage'), 'MethodologyPage');
const SourcesPage = page(() => import('./pages/SourcesPage'), 'SourcesPage');
const NotFoundPage = page(() => import('./pages/NotFoundPage'), 'NotFoundPage');
const UiSheetPage = import.meta.env.DEV
  ? page(() => import('./pages/UiSheetPage'), 'UiSheetPage')
  : null;

/** Screens that are a full-bleed map: no footer, the header is the only chrome. */
const MAP_SCREENS = ['/kartica', '/planiranje'];

function Header() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const current = (href: string) => (pathname.startsWith(href) ? 'page' : undefined);

  function focusSearch() {
    const field = document.querySelector<HTMLInputElement>('input[role="combobox"]');
    if (field && pathname === '/') field.focus();
    else navigate('/');
  }

  return (
    <header className="na-header">
      <div className="na-header__inner">
        <Link className="na-brand" to="/" aria-label="Blizu.zg – početna">
          <LogoMark />
          <span>
            Blizu<span className="na-brand__zg">.zg</span>
          </span>
        </Link>
        <nav aria-label="Glavna navigacija" style={{ display: 'contents' }}>
          <ul className="na-nav">
            <li>
              <Link to="/metodologija" aria-current={current('/metodologija')}>
                Kako radi?
              </Link>
            </li>
            <li>
              <Link to="/izvori" aria-current={current('/izvori')}>
                Otvoreni podaci
              </Link>
            </li>
          </ul>
        </nav>
        <div className="na-header__end">
          <Link
            to="/planiranje"
            className="na-btn na-btn--ghost na-btn--sm"
            aria-current={current('/planiranje')}
          >
            Planerski način
          </Link>
          <button
            type="button"
            className="na-iconbtn"
            aria-label="Pretraži adresu"
            onClick={focusSearch}
          >
            <Icon name="search" size={18} />
          </button>
        </div>
      </div>
    </header>
  );
}

export function App() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.documentElement.lang = 'hr';
  }, []);
  const mapScreen = MAP_SCREENS.some((p) => pathname.startsWith(p));
  return (
    <div className="dt-shell">
      <SkipLink />
      <Header />
      <main id="main" tabIndex={-1} style={{ flex: 1, outline: 'none' }}>
        <Suspense
          fallback={
            <div className="na-wrap" style={{ minHeight: '60vh' }}>
              <LoadingSkeleton lines={4} label="Učitavam stranicu…" />
            </div>
          }
        >
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/kartica" element={<CardPage />} />
            <Route path="/usporedi" element={<ComparePage />} />
            <Route path="/planiranje" element={<PlanningPage />} />
            <Route path="/metodologija" element={<MethodologyPage />} />
            <Route path="/izvori" element={<SourcesPage />} />
            {UiSheetPage ? <Route path="/__ui" element={<UiSheetPage />} /> : null}
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </main>
      {mapScreen ? null : (
        <footer
          className="na-footer"
          style={{ borderTop: '1px solid var(--na-line)', padding: '1.5rem 1rem' }}
        >
          <div
            className="na-muted"
            style={{
              maxWidth: '80rem',
              margin: '0 auto',
              display: 'flex',
              flexWrap: 'wrap',
              gap: '0.5rem 1.5rem',
              fontSize: '0.8125rem',
            }}
          >
            <Link to="/izvori">Izvori podataka</Link>
            <a
              href="https://spdx.org/licenses/EUPL-1.2.html"
              target="_blank"
              rel="noopener noreferrer"
            >
              Izvorni kôd: EUPL-1.2
            </a>
            <span>
              Karta: © OpenStreetMap contributors. Blizu je prototip nastao za Datathon Portala
              otvorenih podataka 2026.
            </span>
          </div>
        </footer>
      )}
    </div>
  );
}
