import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useLocation } from 'react-router-dom';
import { AlertForm, type AlertFormProps } from './AlertForm';

interface AlertDialogApi {
  /** Open the alert dialog, optionally prefilled from the current page. */
  open: (prefill?: Pick<AlertFormProps, 'oib' | 'query'>) => void;
  isOpen: boolean;
}

const Ctx = createContext<AlertDialogApi>({ open: () => undefined, isOpen: false });
export const useAlertDialog = () => useContext(Ctx);

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

/** Accessible modal: focus is trapped, Esc and the overlay close it, focus returns to the opener. */
export function AlertDialogProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ open: boolean; prefill: AlertFormProps }>({
    open: false,
    prefill: {},
  });
  const opener = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();
  const { pathname } = useLocation();
  // on a company page the OIB is known: every "send me relevant tenders" button prefills it
  const pageOib = /^\/tvrtka\/(\d{11})$/.exec(pathname)?.[1];

  const open = useCallback(
    (prefill?: Pick<AlertFormProps, 'oib' | 'query'>) => {
      opener.current = document.activeElement as HTMLElement | null;
      setState({ open: true, prefill: prefill ?? (pageOib ? { oib: pageOib } : {}) });
    },
    [pageOib],
  );
  const close = useCallback(() => {
    setState((s) => ({ ...s, open: false }));
    opener.current?.focus();
  }, []);

  useEffect(() => {
    if (!state.open) return;
    const node = dialogRef.current;
    node?.querySelector<HTMLElement>('input, button')?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        close();
      } else if (e.key === 'Tab' && node) {
        const items = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
          (el) => el.offsetParent !== null,
        );
        const first = items[0];
        const last = items[items.length - 1];
        if (!first || !last) return;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey, true);
    return () => {
      document.removeEventListener('keydown', onKey, true);
      document.body.style.overflow = previous;
    };
  }, [state.open, close]);

  const value = useMemo(() => ({ open, isOpen: state.open }), [open, state.open]);
  return (
    <Ctx.Provider value={value}>
      {children}
      {state.open ? (
        <div
          className="nb-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) close();
          }}
        >
          <div
            ref={dialogRef}
            className="nb-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
          >
            <div className="flex items-start justify-between gap-3">
              <h2 id={titleId} className="text-2xl">
                Pošalji mi relevantne natječaje
              </h2>
              <button type="button" className="nb-btn nb-btn--light nb-btn--sm" onClick={close}>
                Zatvori
              </button>
            </div>
            <p className="mb-4 mt-1">
              Javit ćemo vam e-poštom čim se pojavi natječaj čija prilagodba dosegne vaš prag. Svaki
              natječaj šaljemo samo jednom.
            </p>
            <AlertForm {...state.prefill} />
          </div>
        </div>
      ) : null}
    </Ctx.Provider>
  );
}
