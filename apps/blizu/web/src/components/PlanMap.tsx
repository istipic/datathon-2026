import { MapView } from '@dt/ui';
import { Marker, type GeoJSONSource, type Map as MapLibreMap } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import { useEffect, useRef, useState } from 'react';
import { NEED_COLORS, NO_NEED_COLOR, ZAGREB_BOUNDS } from '../lib/legend';
import type { NeedCollection, OptimiseSite } from '../lib/types';

interface Props {
  need: NeedCollection | undefined;
  sites: OptimiseSite[];
}

/** Choropleth of unmet need per 1 km cell plus markers for the suggested new sites. */
export function PlanMap({ need, sites }: Props) {
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const markers = useRef<Marker[]>([]);

  const fitted = useRef(false);
  useEffect(() => {
    if (!map || fitted.current) return;
    fitted.current = true;
    map.fitBounds(ZAGREB_BOUNDS, { padding: 16, duration: 0 });
  }, [map]);

  useEffect(() => {
    if (!map || !need) return;
    const edges = [...new Set(need.summary.breaks.map((b) => Math.round(b * 10) / 10))]
      .filter((b) => b > 0)
      .sort((a, b) => a - b);
    const fill: unknown =
      edges.length === 0
        ? ['case', ['<=', ['get', 'unmet'], 0], NO_NEED_COLOR, NEED_COLORS[2]]
        : [
            'case',
            ['<=', ['get', 'unmet'], 0],
            NO_NEED_COLOR,
            [
              'step',
              ['get', 'unmet'],
              NEED_COLORS[0],
              ...edges.flatMap((e, i) => [e, NEED_COLORS[i + 1]]),
            ],
          ];
    const apply = () => {
      const existing = map.getSource('need') as GeoJSONSource | undefined;
      if (existing) {
        existing.setData(need as unknown as FeatureCollection);
      } else {
        map.addSource('need', { type: 'geojson', data: need as unknown as FeatureCollection });
        map.addLayer({
          id: 'need-fill',
          type: 'fill',
          source: 'need',
          paint: { 'fill-color': fill as never, 'fill-opacity': 0.72 },
        });
        map.addLayer({
          id: 'need-line',
          type: 'line',
          source: 'need',
          paint: { 'line-color': '#475569', 'line-width': 0.5, 'line-opacity': 0.6 },
        });
      }
      if (map.getLayer('need-fill')) map.setPaintProperty('need-fill', 'fill-color', fill as never);
    };
    if (map.isStyleLoaded()) apply();
    else map.once('idle', apply);
  }, [map, need]);

  useEffect(() => {
    if (!map) return;
    markers.current.forEach((m) => m.remove());
    markers.current = sites.map((site, i) => {
      const el = document.createElement('div');
      el.className = 'blizu-site';
      el.setAttribute('role', 'img');
      el.setAttribute(
        'aria-label',
        `Predložena lokacija ${i + 1}${site.street ? `, ${site.street}` : ''}: ${site.newly_covered} osoba`,
      );
      el.textContent = `+${site.newly_covered.toLocaleString('hr-HR')} osoba`;
      return new Marker({ element: el }).setLngLat([site.lon, site.lat]).addTo(map);
    });
    return () => {
      markers.current.forEach((m) => m.remove());
      markers.current = [];
    };
  }, [map, sites]);

  return (
    <MapView
      ariaLabel="Karta nezadovoljene potrebe po ćelijama od 1 km"
      onLoad={setMap}
      className="blizu-map"
    />
  );
}
