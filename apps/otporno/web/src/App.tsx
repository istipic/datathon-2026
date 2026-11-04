import { LoadingSkeleton, SkipLink } from '@dt/ui';
import { Suspense, lazy, useEffect } from 'react';
import { Link, Route, Routes, useLocation } from 'react-router-dom';
import { Logo, NavIcon } from './components/icons';

const page = <T extends string>(load: () => Promise<Record<T, React.ComponentType>>, name: T) =>
  lazy(() => load().then((m) => ({ default: m[name] })));
const HomePage = page(() => import('./pages/HomePage'), 'HomePage');
const PassportPage = page(() => import('./pages/PassportPage'), 'PassportPage');
const MunicipalityPage = page(() => import('./pages/MunicipalityPage'), 'MunicipalityPage');
const MunicipalitiesPage = page(() => import('./pages/MunicipalitiesPage'), 'MunicipalitiesPage');
const MethodologyPage = page(() => import('./pages/MethodologyPage'), 'MethodologyPage');
const SourcesPage = page(() => import('./pages/SourcesPage'), 'SourcesPage');
const NotFoundPage = page(() => import('./pages/NotFoundPage'), 'NotFoundPage');

const NAV = [
  { label: 'Moja adresa', short: 'Adresa', href: '/', icon: 'home' as const },
  { label: 'Općine i gradovi', short: 'Općine', href: '/opcina', icon: 'town' as const },
  { label: 'Metodologija', short: 'Metoda', href: '/metodologija', icon: 'book' as const },
  { label: 'Izvori podataka', short: 'Izvori', href: '/izvori', icon: 'db' as const },
];

function isCurrent(href: string, pathname: string): boolean {
  if (href === '/') return pathname === '/' || pathname.startsWith('/putovnica');
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
    <div className="ot-shell">
      <SkipLink />
      <header className="ot-rail">
        <div>
          <Link to="/" className="ot-brand" aria-label="Otporko, početna stranica">
            <Logo />
            <span>Otporko</span>
          </Link>
          <p className="ot-rail-tag mt-2 text-sm" style={{ color: 'rgb(199 210 254)' }}>
            Putovnica rizika od poplave i vrućine za svaku adresu u Hrvatskoj.
          </p>
        </div>
        <nav className="ot-nav" aria-label="Glavna navigacija">
          {NAV.map((item) => (
            <Link
              key={item.href}
              to={item.href}
              aria-current={isCurrent(item.href, pathname) ? 'page' : undefined}
            >
              <NavIcon name={item.icon} />
              <span className="hidden lg:inline">{item.label}</span>
              <span className="lg:hidden">{item.short}</span>
            </Link>
          ))}
        </nav>
        <p className="ot-rail-foot mt-auto text-sm" style={{ color: 'rgb(199 210 254)' }}>
          Datathon Portala otvorenih podataka 2026. Izvorni kôd: EUPL-1.2.
        </p>
      </header>
      <main id="main" className="ot-main" tabIndex={-1}>
        <div className="ot-wrap">
          <Suspense fallback={<LoadingSkeleton lines={4} label="Učitavam stranicu…" />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/putovnica" element={<PassportPage />} />
              <Route path="/opcina" element={<MunicipalitiesPage />} />
              <Route path="/opcina/:lau" element={<MunicipalityPage />} />
              <Route path="/metodologija" element={<MethodologyPage />} />
              <Route path="/izvori" element={<SourcesPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </div>
      </main>
    </div>
  );
}
