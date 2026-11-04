import { MapView } from '@dt/ui';
import { Marker, type Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';
import { WMS_SCENARIOS, legendUrl, wmsTileUrl } from '../lib/bands';
import type { FloodBlock } from '../lib/types';

interface Props {
  lat: number;
  lon: number;
  flood: FloodBlock;
}

type Key = (typeof WMS_SCENARIOS)[number]['key'];

/**
 * Hrvatske vode flood hazard maps (2019) as a WMS overlay on the base map, with a switch per scenario and an
 * opacity slider. The overlay is for looking: no flood class is derived from it (docs/adr/0007).
 */
export function FloodMap({ lat, lon, flood }: Props) {
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [opacity, setOpacity] = useState(0.7);
  const [on, setOn] = useState<Record<Key, boolean>>({ high: true, medium: true, low: false });
  const [legendFailed, setLegendFailed] = useState(false);
  // the three scenario legends are the same graphic (depth classes): show one
  const legendKey: Key = WMS_SCENARIOS.find((s) => on[s.key])?.key ?? 'high';

  function onLoad(map: MapLibreMap) {
    mapRef.current = map;
    for (const s of WMS_SCENARIOS) {
      map.addSource(`hv-${s.key}`, {
        type: 'raster',
        tiles: [wmsTileUrl(flood.wms.url, flood.wms.layers[s.key])],
        tileSize: 256,
        attribution: 'Hrvatske vode, 2019.',
      });
      map.addLayer({
        id: `hv-${s.key}`,
        type: 'raster',
        source: `hv-${s.key}`,
        paint: { 'raster-opacity': 0.7 },
        layout: { visibility: s.key === 'low' ? 'none' : 'visible' },
      });
    }
    const el = document.createElement('div');
    el.className = 'ot-pin';
    el.setAttribute('role', 'img');
    el.setAttribute('aria-label', 'Vaša adresa');
    new Marker({ element: el, anchor: 'bottom' }).setLngLat([lon, lat]).addTo(map);
    map.jumpTo({ center: [lon, lat], zoom: 13.5 });
    setReady(true);
  }

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    for (const s of WMS_SCENARIOS) {
      map.setLayoutProperty(`hv-${s.key}`, 'visibility', on[s.key] ? 'visible' : 'none');
      map.setPaintProperty(`hv-${s.key}`, 'raster-opacity', opacity);
    }
  }, [on, opacity, ready]);

  return (
    <div>
      <fieldset className="mb-3 grid gap-2 border-0 p-0 sm:grid-cols-3">
        <legend className="mb-1 text-base font-bold">Scenariji plavljenja na karti</legend>
        {WMS_SCENARIOS.map((s) => (
          <label
            key={s.key}
            className="flex min-h-[44px] items-center gap-2 rounded-lg border border-neutral-300 bg-white px-3"
          >
            <input
              type="checkbox"
              className="h-5 w-5"
              style={{ accentColor: '#1E3A8A' }}
              checked={on[s.key]}
              onChange={(e) => setOn((p) => ({ ...p, [s.key]: e.target.checked }))}
            />
            <span>
              <span className="block font-bold">{s.label}</span>
              <span className="block text-sm text-neutral-700">{s.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <div className="ot-map">
        <MapView
          ariaLabel="Karta opasnosti od poplava Hrvatskih voda s vašom adresom"
          center={[lon, lat]}
          zoom={13.5}
          onLoad={onLoad}
        />
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="flood-opacity" className="block text-sm font-bold">
            Prozirnost sloja poplava: {Math.round(opacity * 100)} %
          </label>
          <input
            id="flood-opacity"
            type="range"
            min={0.1}
            max={1}
            step={0.05}
            value={opacity}
            onChange={(e) => setOpacity(Number(e.target.value))}
          />
        </div>
        <figure className="m-0 text-sm" aria-label="Legenda">
          {legendFailed ? (
            <p className="text-neutral-700">Legenda Hrvatskih voda trenutno nije dostupna.</p>
          ) : (
            <img
              src={legendUrl(flood.wms.url, flood.wms.layers[legendKey])}
              alt="Legenda Hrvatskih voda: boje označavaju dubinu vode; ista legenda vrijedi za sva tri scenarija"
              onError={() => setLegendFailed(true)}
              height={40}
            />
          )}
        </figure>
      </div>
      <p className="mt-3 text-sm text-neutral-700">
        {flood.disclaimer} Prikazane su karte iz {flood.map_year}. godine; stvarna situacija na
        terenu može se razlikovati.
      </p>
    </div>
  );
}
