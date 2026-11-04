import { AppShell, LoadingSkeleton, type ShellLinkProps } from '@dt/ui';
import { Suspense, lazy } from 'react';
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
  { label: 'Za tvrtke', href: '/' },
  { label: 'Za naručitelje', href: '/narucitelj' },
  { label: 'Metodologija', href: '/metodologija' },
  { label: 'Izvori podataka', href: '/izvori' },
];

export function App() {
  const { pathname } = useLocation();
  const nav = NAV.map((item) => ({
    ...item,
    current:
      item.href === '/'
        ? pathname === '/' || pathname.startsWith('/tvrtka') || pathname.startsWith('/natjecaj')
        : pathname.startsWith(item.href),
  }));
  return (
    <AppShell
      brandName="NabavaRadar"
      logo="◎"
      nav={nav}
      sourcesHref="/izvori"
      linkComponent={RouterLink}
      footer={
        <span>
          Podaci: TED, Sudski registar, CPV 2008. NabavaRadar je prototip nastao za Datathon Portala
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
          <Route path="/tvrtka/:oib" element={<CompanyPage />} />
          <Route path="/natjecaj/:pubNo" element={<NoticePage />} />
          <Route path="/narucitelj" element={<BuyerPage />} />
          <Route path="/metodologija" element={<MethodologyPage />} />
          <Route path="/izvori" element={<SourcesPage />} />
          <Route path="/pretplata/potvrda" element={<ConfirmPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
