import { EmptyState, ErrorState, LoadingSkeleton } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useId, useState, type KeyboardEvent } from 'react';
import { api } from '../lib/api';
import type { GeocodeItem } from '../lib/types';

export const DEBOUNCE_MS = 400;
const MIN_CHARS = 3;

interface Props {
  onSelect: (item: GeocodeItem) => void;
  label?: string;
  initialValue?: string;
  placeholder?: string;
  autoFocus?: boolean;
}

/** Address autocomplete (ARIA combobox) over `/api/v1/geocode`, anywhere in Croatia, debounced 400 ms. */
export function AddressSearch({
  onSelect,
  label = 'Adresa bilo gdje u Hrvatskoj',
  initialValue = '',
  placeholder = 'npr. Trg bana Josipa Jelačića, Karlovac',
  autoFocus,
}: Props) {
  const id = useId();
  const [text, setText] = useState(initialValue);
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);

  useEffect(() => {
    const trimmed = text.trim();
    const timer = setTimeout(
      () => setDebounced(trimmed.length >= MIN_CHARS ? trimmed : ''),
      DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [text]);

  const query = useQuery({
    queryKey: ['geocode', debounced],
    queryFn: ({ signal }) => api.geocode(debounced, signal),
    enabled: debounced.length >= MIN_CHARS,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const results = query.data?.results ?? [];
  const showPanel = open && debounced.length >= MIN_CHARS && text.trim() === debounced;

  function choose(item: GeocodeItem) {
    setText(item.label.split(',').slice(0, 3).join(',').trim() || item.title);
    setOpen(false);
    setActive(-1);
    onSelect(item);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setOpen(true);
      setActive((i) => (results.length ? (i + 1) % results.length : -1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => (results.length ? (i <= 0 ? results.length - 1 : i - 1) : -1));
    } else if (event.key === 'Enter') {
      const item = results[active] ?? (results.length === 1 ? results[0] : undefined);
      if (item && showPanel) {
        event.preventDefault();
        choose(item);
      }
    } else if (event.key === 'Escape') {
      setOpen(false);
      setActive(-1);
    }
  }

  const listId = `${id}-list`;
  return (
    <div className="relative w-full text-neutral-900">
      <label htmlFor={`${id}-input`} className="mb-1 block text-sm font-bold">
        {label}
      </label>
      <input
        id={`${id}-input`}
        type="text"
        role="combobox"
        aria-expanded={showPanel && results.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${id}-opt-${active}` : undefined}
        autoComplete="off"
        autoFocus={autoFocus}
        maxLength={120}
        placeholder={placeholder}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        className="w-full min-h-[52px] rounded-lg border-2 border-neutral-700 bg-white px-4 py-2 text-lg text-neutral-900 placeholder:text-neutral-600"
      />
      <p className="dt-sr-only" aria-live="polite">
        {showPanel && query.isSuccess
          ? results.length > 0
            ? `${results.length} prijedloga adresa`
            : 'Nema rezultata'
          : ''}
      </p>
      <div id={listId} className="mt-2">
        {showPanel && query.isFetching ? (
          <LoadingSkeleton lines={2} label="Tražim adresu…" />
        ) : null}
        {showPanel && query.isError ? (
          <ErrorState
            message={query.error instanceof Error ? query.error.message : 'Pretraga nije uspjela.'}
            onRetry={() => void query.refetch()}
          />
        ) : null}
        {showPanel && query.isSuccess && results.length === 0 ? (
          <EmptyState
            title="Nema rezultata"
            body="Nismo našli tu adresu. Pokušajte s ulicom, kućnim brojem i mjestom, npr. „Trg bana Josipa Jelačića, Karlovac”."
          />
        ) : null}
        {showPanel && query.isSuccess && results.length > 0 ? (
          <>
            <ul
              role="listbox"
              aria-label="Prijedlozi adresa"
              className="overflow-hidden rounded-lg border border-neutral-300 bg-white shadow-md"
            >
              {results.map((item, i) => (
                <li
                  key={`${item.lat},${item.lon},${i}`}
                  id={`${id}-opt-${i}`}
                  role="option"
                  aria-selected={i === active}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    choose(item);
                  }}
                  onMouseEnter={() => setActive(i)}
                  className={[
                    'min-h-[44px] cursor-pointer px-4 py-3 text-base',
                    i === active
                      ? 'bg-brand-700 text-white'
                      : 'text-neutral-900 hover:bg-neutral-100',
                  ].join(' ')}
                >
                  {item.title}
                  <span
                    className={
                      i === active ? 'block text-sm text-white' : 'block text-sm text-neutral-600'
                    }
                  >
                    {item.label}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-sm" style={{ color: 'inherit' }}>
              {query.data?.attribution}
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
}
