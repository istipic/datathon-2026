import { AppShell, type ShellLinkProps } from '@dt/ui';
import { Link, Route, Routes, useLocation } from 'react-router-dom';
import { CardPage } from './pages/CardPage';
import { ComparePage } from './pages/ComparePage';
import { HomePage } from './pages/HomePage';
import { MethodologyPage } from './pages/MethodologyPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { PlanningPage } from './pages/PlanningPage';
import { SourcesPage } from './pages/SourcesPage';

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
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/kartica" element={<CardPage />} />
        <Route path="/usporedi" element={<ComparePage />} />
        <Route path="/planiranje" element={<PlanningPage />} />
        <Route path="/metodologija" element={<MethodologyPage />} />
        <Route path="/izvori" element={<SourcesPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  );
}
