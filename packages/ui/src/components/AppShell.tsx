import { useEffect, type ReactNode } from 'react';
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

export interface AppShellProps {
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
          <a className="dt-brand" href={homeHref}>
            {logo ? <span aria-hidden="true">{logo}</span> : null}
            <span>{brandName}</span>
          </a>
          {nav.length > 0 ? (
            <nav aria-label="Glavna navigacija">
              <ul className="dt-nav">
                {nav.map((item) => (
                  <li key={item.href}>
                    <a href={item.href} aria-current={item.current ? 'page' : undefined}>
                      {item.label}
                    </a>
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
          <a href={sourcesHref}>Izvori podataka</a>
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
