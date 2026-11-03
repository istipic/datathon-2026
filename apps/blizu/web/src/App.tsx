import { AppShell, type ShellLinkProps } from '@dt/ui';
import { Suspense, lazy } from 'react';
import { Link, Route, Routes, useLocation } from 'react-router-dom';
import { LoadingSkeleton } from '@dt/ui';

const page = <T extends string>(load: () => Promise<Record<T, React.ComponentType>>, name: T) =>
  lazy(() => load().then((m) => ({ default: m[name] })));
const HomePage = page(() => import('./pages/HomePage'), 'HomePage');
const CardPage = page(() => import('./pages/CardPage'), 'CardPage');
const ComparePage = page(() => import('./pages/ComparePage'), 'ComparePage');
const PlanningPage = page(() => import('./pages/PlanningPage'), 'PlanningPage');
const MethodologyPage = page(() => import('./pages/MethodologyPage'), 'MethodologyPage');
const SourcesPage = page(() => import('./pages/SourcesPage'), 'SourcesPage');
const NotFoundPage = page(() => import('./pages/NotFoundPage'), 'NotFoundPage');

/** Adapter so the shared AppShell navigates client-side. */
function RouterLink({ href, children, ...rest }: ShellLinkProps) {
  return (
    <Link to={href} {...rest}>
      {children}
    </Link>
  );
}

const NAV = [
  { label: 'Početna', href: '/' },
  { label: 'Planiranje', href: '/planiranje' },
  { label: 'Metodologija', href: '/metodologija' },
  { label: 'Izvori podataka', href: '/izvori' },
];

export function App() {
  const { pathname } = useLocation();
  const nav = NAV.map((item) => ({
    ...item,
    current: item.href === '/' ? pathname === '/' : pathname.startsWith(item.href),
  }));
  return (
    <AppShell
      brandName="Blizu"
      logo="●"
      nav={nav}
      sourcesHref="/izvori"
      linkComponent={RouterLink}
      footer={
        <span>
          Karta: © OpenStreetMap contributors. Blizu je prototip nastao za Datathon Portala
          otvorenih podataka 2026.
        </span>
      }
    >
      <Suspense
        fallback={
          <div style={{ minHeight: '100vh' }}>
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
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
