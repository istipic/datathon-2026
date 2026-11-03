import { useEffect, type ComponentType, type ReactNode } from 'react';
import { SkipLink } from './SkipLink';

export interface NavItem {
  label: string;
  href: string;
  /** Marks the current page (sets aria-current="page"). */
  current?: boolean;
}

export interface LicenceItem {
  label: string;
  href: string;
}

/** Props the shell passes to its internal link component (a plain <a> by default). */
export interface ShellLinkProps {
  href: string;
  className?: string;
  'aria-current'?: 'page';
  target?: string;
  rel?: string;
  children: ReactNode;
}

export interface AppShellProps {
  /** Replace <a> for internal links (e.g. a react-router adapter) to avoid full page loads. */
  linkComponent?: ComponentType<ShellLinkProps>;
  brandName: string;
  logo?: ReactNode;
  /** Where the brand links to (default "/"). */
  homeHref?: string;
  nav?: NavItem[];
  /** Link target of the footer's "Izvori podataka" link. */
  sourcesHref?: string;
  /** Licences shown in the footer; defaults to the source-code licence. */
  licences?: LicenceItem[];
  /** Extra footer content (e.g. a disclaimer). */
  footer?: ReactNode;
  children: ReactNode;
}

function DefaultLink({ children, ...rest }: ShellLinkProps) {
  return <a {...rest}>{children}</a>;
}

export const DEFAULT_LICENCES: LicenceItem[] = [
  { label: 'Izvorni kôd: EUPL-1.2', href: 'https://spdx.org/licenses/EUPL-1.2.html' },
];

/**
 * Page frame: skip link, header with brand + navigation, main landmark and footer with
 * licences and a link to the data sources page. Also makes sure <html lang="hr"> is set.
 */
export function AppShell({
  brandName,
  logo,
  homeHref = '/',
  nav = [],
  sourcesHref = '/izvori-podataka',
  licences = DEFAULT_LICENCES,
  footer,
  linkComponent: Link = DefaultLink,
  children,
}: AppShellProps) {
  useEffect(() => {
    document.documentElement.lang = 'hr';
  }, []);

  return (
    <div className="dt-shell">
      <SkipLink />
      <header className="dt-header">
        <div className="dt-header__inner">
          <Link className="dt-brand" href={homeHref}>
            {logo ? <span aria-hidden="true">{logo}</span> : null}
            <span>{brandName}</span>
          </Link>
          {nav.length > 0 ? (
            <nav aria-label="Glavna navigacija">
              <ul className="dt-nav">
                {nav.map((item) => (
                  <li key={item.href}>
                    <Link href={item.href} aria-current={item.current ? 'page' : undefined}>
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ) : null}
        </div>
      </header>
      <main id="main" className="dt-main" tabIndex={-1}>
        {children}
      </main>
      <footer className="dt-footer">
        <div className="dt-footer__inner">
          <Link href={sourcesHref}>Izvori podataka</Link>
          {licences.map((licence) => (
            <a key={licence.href} href={licence.href} target="_blank" rel="noopener noreferrer">
              {licence.label}
            </a>
          ))}
          {footer}
        </div>
      </footer>
    </div>
  );
}
