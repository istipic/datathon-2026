import { MapView } from '@dt/ui';
import { LngLatBounds, Marker, Popup, type Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { CATEGORY_SHORT } from '../lib/labels';
import type { CategoryId } from '../lib/types';
import { CategoryIcon } from './CategoryIcon';

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
}

function reducedMotion(): boolean {
  return (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

function pinElement(label: string): HTMLElement {
  const el = document.createElement('div');
  el.className = 'blizu-pin';
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', label);
  el.innerHTML =
    '<svg width="34" height="44" viewBox="0 0 34 44" aria-hidden="true"><path d="M17 1C8.7 1 2 7.5 2 15.7 2 26.5 17 43 17 43s15-16.5 15-27.3C32 7.5 25.300 1 17 1z" fill="#B45309" stroke="#fff" stroke-width="2"/><circle cx="17" cy="16" r="5.5" fill="#fff"/></svg>';
  return el;
}

function placeElement(place: MapPlace): HTMLElement {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'blizu-marker';
  el.setAttribute('aria-label', `${CATEGORY_SHORT[place.category]}: ${place.name}`);
  el.innerHTML = renderToStaticMarkup(<CategoryIcon category={place.category} size={20} />);
  return el;
}

/** Map of one address: pin, the nearest facility of each category, fly-to on request. */
export function MapPanel({ origin, places, focus }: Props) {
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const popup = useRef<Popup | null>(null);

  useEffect(() => {
    if (!map) return;
    markers.current.forEach((m) => m.remove());
    markers.current = [];
    const bounds = new LngLatBounds([origin.lon, origin.lat], [origin.lon, origin.lat]);

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
      markers.current.push(new Marker({ element }).setLngLat([place.lon, place.lat]).addTo(map));
      bounds.extend([place.lon, place.lat]);
    }
    map.fitBounds(bounds, { padding: 70, maxZoom: 16, duration: reducedMotion() ? 0 : 600 });
    return () => {
      markers.current.forEach((m) => m.remove());
      markers.current = [];
    };
  }, [map, origin.lon, origin.lat, origin.label, places]);

  useEffect(() => {
    if (!map || !focus) return;
    if (reducedMotion()) map.jumpTo({ center: [focus.lon, focus.lat], zoom: 16 });
    else map.flyTo({ center: [focus.lon, focus.lat], zoom: 16 });
  }, [map, focus]);

  return (
    <MapView
      ariaLabel="Karta s adresom i najbližim objektima"
      onLoad={setMap}
      className="blizu-map"
    />
  );
}
