import { MapView } from '@dt/ui';
import { LngLatBounds, Marker, type GeoJSONSource, type Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';
import { PRIORITY_FILL, PRIORITY_LABEL } from '../lib/bands';
import type { CellCollection, CellProperties, CoolingResult } from '../lib/types';
import { fmtInt } from '../lib/format';

interface Props {
  cells: CellCollection;
  sites: CoolingResult['sites'];
  onSelect: (cell: CellProperties | null) => void;
}

function fitTo(map: MapLibreMap, cells: CellCollection) {
  const b = new LngLatBounds();
  for (const f of cells.features)
    for (const [x, y] of f.geometry.coordinates[0] ?? []) b.extend([x as number, y as number]);
  if (!b.isEmpty()) map.fitBounds(b, { padding: 30, duration: 0 });
}

/** Priority choropleth of the 1 km cells (five classes, quantiles) with the proposed cooling-centre sites. */
export function PriorityMap({ cells, sites, onSelect }: Props) {
  const mapRef = useRef<MapLibreMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const fitted = useRef(false);
  const [ready, setReady] = useState(false);

  function onLoad(map: MapLibreMap) {
    mapRef.current = map;
    map.addSource('cells', { type: 'geojson', data: cells as never });
    const colour: unknown[] = ['match', ['get', 'priority_class']];
    PRIORITY_FILL.forEach((c, i) => colour.push(i - 1, c));
    colour.push(PRIORITY_FILL[0]);
    map.addLayer({
      id: 'cells-fill',
      type: 'fill',
      source: 'cells',
      paint: { 'fill-color': colour as never, 'fill-opacity': 0.78 },
    });
    map.addLayer({
      id: 'cells-line',
      type: 'line',
      source: 'cells',
      paint: { 'line-color': '#57534E', 'line-width': 0.6, 'line-opacity': 0.6 },
    });
    map.on('click', 'cells-fill', (e) => {
      const p = e.features?.[0]?.properties as CellProperties | undefined;
      onSelect(p ?? null);
    });
    map.on('mouseenter', 'cells-fill', () => (map.getCanvas().style.cursor = 'pointer'));
    map.on('mouseleave', 'cells-fill', () => (map.getCanvas().style.cursor = ''));
    fitTo(map, cells);
    fitted.current = true;
    setReady(true);
  }

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource('cells') as GeoJSONSource | undefined)?.setData(cells as never);
    if (!fitted.current) fitTo(map, cells);
  }, [cells, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    markers.current.forEach((m) => m.remove());
    markers.current = sites.map((s, i) => {
      const el = document.createElement('div');
      el.className = 'ot-site';
      el.textContent = String(i + 1);
      el.setAttribute('role', 'img');
      el.setAttribute('aria-label', `Prijedlog ${i + 1}: ${s.name ?? 'javna zgrada'}`);
      return new Marker({ element: el }).setLngLat([s.lon, s.lat]).addTo(map);
    });
  }, [sites, ready]);

  return (
    <div>
      <div className="ot-map" style={{ height: '30rem' }}>
        <MapView ariaLabel="Karta prioriteta po ćelijama od 1 km" onLoad={onLoad} />
      </div>
      <ul
        className="mt-3 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-sm"
        aria-label="Legenda prioriteta"
      >
        {PRIORITY_FILL.map((c, i) => (
          <li key={c} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="inline-block h-4 w-6 border border-neutral-600"
              style={{ background: c }}
            />
            {PRIORITY_LABEL[i]}
          </li>
        ))}
        {sites.length > 0 ? (
          <li className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="ot-site"
              style={{ width: 20, height: 20, fontSize: 12 }}
            >
              1
            </span>
            Predloženi centar
          </li>
        ) : null}
      </ul>
      <p className="mt-2 text-sm text-neutral-700">
        Ukupno {fmtInt(cells.summary.cells)} naseljenih ćelija, {fmtInt(cells.summary.pop_total)}{' '}
        stanovnika.
      </p>
    </div>
  );
}
