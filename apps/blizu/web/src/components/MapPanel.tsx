import { MapView } from '@dt/ui';
import { LngLatBounds, Marker, Popup, type Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { Link } from 'react-router-dom';
import { CATEGORY_SHORT } from '../lib/labels';
import type { CategoryId } from '../lib/types';
import { CategoryIcon } from './CategoryIcon';
import { Icon } from './ui';

/** OpenFreeMap dark style (verified 2026-11-05, see apps/blizu/data/evidence). */
export const DARK_STYLE_URL = 'https://tiles.openfreemap.org/styles/dark';

export interface MapPlace {
  category: CategoryId;
  name: string;
  address: string | null;
  lon: number;
  lat: number;
}
export interface MapFocus {
  lon: number;
  lat: number;
  /** Changes on every request so that the same place can be focused again. */
  key: number;
}

interface Props {
  origin: { lon: number; lat: number; label?: string };
  places: MapPlace[];
  focus?: MapFocus | null;
  /** Link of the floating call to action ("Vidi analizu potreba kvarta"). */
  plannerHref?: string;
  /** Receives the MapLibre instance once the style is ready (scenes attach to it). */
  onMap?: (map: MapLibreMap) => void;
  /** Extra overlays (scene bar, time slider) rendered above the map. */
  children?: React.ReactNode;
  /** Extra floating buttons below the zoom/locate stack (e.g. 3D). */
  extraControls?: React.ReactNode;
  onFallback?: () => void;
}

function reducedMotion(): boolean {
  return (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

function pinElement(label: string): HTMLElement {
  const el = document.createElement('div');
  el.className = 'na-pin';
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', label);
  const card = document.createElement('span');
  card.className = 'na-pinlabel';
  card.textContent = label;
  card.setAttribute('aria-hidden', 'true');
  el.append(card);
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', '34');
  svg.setAttribute('height', '44');
  svg.setAttribute('viewBox', '0 0 34 44');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML =
    '<path d="M17 1C8.7 1 2 7.5 2 15.7 2 26.5 17 43 17 43s15-16.5 15-27.3C32 7.5 25.3 1 17 1z" fill="#22D3EE" stroke="#07090D" stroke-width="2"/><circle cx="17" cy="16" r="5.500" fill="#07090D"/>';
  el.append(svg);
  return el;
}

function placeElement(place: MapPlace): HTMLElement {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'blizu-marker';
  el.setAttribute('aria-label', `${CATEGORY_SHORT[place.category]}: ${place.name}`);
  el.innerHTML = renderToStaticMarkup(<CategoryIcon category={place.category} size={18} />);
  return el;
}

/** Map of one address: pin, the nearest facility of each category, fly-to on request, floating controls. */
export function MapPanel({
  origin,
  places,
  focus,
  plannerHref,
  onMap,
  children,
  extraControls,
  onFallback,
}: Props) {
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [showPlaces, setShowPlaces] = useState(true);
  const markers = useRef<Marker[]>([]);
  const placeMarkers = useRef<Marker[]>([]);
  const popup = useRef<Popup | null>(null);
  const bounds = useRef<LngLatBounds | null>(null);

  useEffect(() => {
    if (!map) return;
    markers.current.forEach((m) => m.remove());
    placeMarkers.current.forEach((m) => m.remove());
    markers.current = [];
    placeMarkers.current = [];
    const box = new LngLatBounds([origin.lon, origin.lat], [origin.lon, origin.lat]);

    markers.current.push(
      new Marker({ element: pinElement(origin.label ?? 'Odabrana adresa'), anchor: 'bottom' })
        .setLngLat([origin.lon, origin.lat])
        .addTo(map),
    );
    for (const place of places) {
      const element = placeElement(place);
      element.addEventListener('click', () => {
        popup.current?.remove();
        const content = document.createElement('div');
        const title = document.createElement('strong');
        title.textContent = place.name;
        content.append(title);
        if (place.address) {
          const addr = document.createElement('div');
          addr.textContent = place.address;
          content.append(addr);
        }
        popup.current = new Popup({ offset: 18, closeButton: true })
          .setLngLat([place.lon, place.lat])
          .setDOMContent(content)
          .addTo(map);
      });
      placeMarkers.current.push(
        new Marker({ element }).setLngLat([place.lon, place.lat]).addTo(map),
      );
      box.extend([place.lon, place.lat]);
    }
    bounds.current = box;
    map.fitBounds(box, { padding: 90, maxZoom: 16, duration: reducedMotion() ? 0 : 600 });
    return () => {
      markers.current.forEach((m) => m.remove());
      placeMarkers.current.forEach((m) => m.remove());
      markers.current = [];
      placeMarkers.current = [];
    };
  }, [map, origin.lon, origin.lat, origin.label, places]);

  useEffect(() => {
    for (const m of placeMarkers.current) {
      m.getElement().style.display = showPlaces ? '' : 'none';
    }
  }, [showPlaces, places, map]);

  useEffect(() => {
    if (!map || !focus) return;
    if (reducedMotion()) map.jumpTo({ center: [focus.lon, focus.lat], zoom: 16 });
    else map.flyTo({ center: [focus.lon, focus.lat], zoom: 16 });
  }, [map, focus]);

  return (
    <>
      <MapView
        ariaLabel="Karta s adresom i najbližim objektima"
        styleUrl={DARK_STYLE_URL}
        navigationControl={false}
        onFallback={onFallback}
        onLoad={(m) => {
          setMap(m);
          onMap?.(m);
        }}
        className="blizu-map"
      />
      <div className="na-mapctl" role="group" aria-label="Kontrole karte">
        <button
          type="button"
          className="na-tip"
          data-tip="Približi"
          aria-label="Približi"
          disabled={!map}
          onClick={() => map?.zoomIn({ essential: false })}
        >
          <Icon name="plus" />
        </button>
        <button
          type="button"
          className="na-tip"
          data-tip="Udalji"
          aria-label="Udalji"
          disabled={!map}
          onClick={() => map?.zoomOut({ essential: false })}
        >
          <Icon name="minus" />
        </button>
        <button
          type="button"
          className="na-tip"
          data-tip="Vrati na adresu"
          aria-label="Vrati na adresu"
          disabled={!map}
          onClick={() =>
            bounds.current &&
            map?.fitBounds(bounds.current, {
              padding: 90,
              maxZoom: 16,
              duration: reducedMotion() ? 0 : 600,
              essential: false,
            })
          }
        >
          <Icon name="locate" />
        </button>
        <button
          type="button"
          className="na-tip"
          data-tip="Objekti na karti"
          aria-label="Prikaži objekte na karti"
          aria-pressed={showPlaces}
          onClick={() => setShowPlaces((v) => !v)}
        >
          <Icon name="layers" />
        </button>
        {extraControls}
      </div>
      {children}
      {plannerHref ? (
        <Link to={plannerHref} className="na-btn na-btn--accent na-cta">
          Vidi analizu potreba kvarta
          <Icon name="arrow" size={18} />
        </Link>
      ) : null}
    </>
  );
}
