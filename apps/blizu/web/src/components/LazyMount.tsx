import { useEffect, useRef, useState, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** Shown (with reserved height) until the placeholder approaches the viewport. */
  placeholder?: ReactNode;
  /** Pre-load distance in px (the map starts loading before it scrolls into view). */
  margin?: number;
  className?: string;
}

/**
 * Mounts its children only when the element is near the viewport. On phones the map sits below the
 * address list, so the heavy map library is not evaluated until the user scrolls toward it.
 * Without IntersectionObserver (old browsers, jsdom) the children mount immediately.
 */
export function LazyMount({ children, placeholder, margin = 300, className }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const supported = typeof IntersectionObserver !== 'undefined';
  const [visible, setVisible] = useState(!supported);

  useEffect(() => {
    if (visible || !ref.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: `${margin}px` },
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [visible, margin]);

  return (
    <div ref={ref} className={className} style={{ minHeight: '24rem', height: '100%' }}>
      {visible ? children : placeholder}
    </div>
  );
}
