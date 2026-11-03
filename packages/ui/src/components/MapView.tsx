import {
  AttributionControl,
  Map as MapLibreMap,
  NavigationControl,
  setWorkerUrl,
  type StyleSpecification,
} from 'maplibre-gl';
// maplibre-gl v6 derives its worker URL from import.meta.url, which breaks once Vite pre-bundles the
// library ("Worker failed to load"). Let Vite bundle the worker and pass its same-origin URL.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { useEffect, useRef, useState } from 'react';

setWorkerUrl(workerUrl);

export const OSM_ATTRIBUTION = '© OpenStreetMap contributors';
export const DEFAULT_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';
export const DEFAULT_FALLBACK_RASTER_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
/** Rough centre and zoom that show all of Croatia. */
export const CROATIA_CENTER: [number, number] = [16.4, 44.5];
export const CROATIA_ZOOM = 6.2;

export interface MapViewProps {
  /** MapLibre style URL (default: OpenFreeMap "liberty"). */
  styleUrl?: string;
  /** Raster tiles used when the vector style cannot be loaded. */
  fallbackRasterUrl?: string;
  center?: [number, number];
  zoom?: number;
  /** Accessible name of the map region. */
  ariaLabel?: string;
  className?: string;
  /** Called once with the MapLibre instance when the map (or its fallback) is ready. */
  onLoad?: (map: MapLibreMap) => void;
}

/** MapLibre style that renders plain OSM raster tiles. */
export function rasterFallbackStyle(tileUrl: string): StyleSpecification {
  return {
    version: 8,
    sources: {
      'osm-raster': {
        type: 'raster',
        tiles: [tileUrl],
        tileSize: 256,
        maxzoom: 19,
        attribution: OSM_ATTRIBUTION,
      },
    },
    layers: [{ id: 'osm-raster', type: 'raster', source: 'osm-raster' }],
  };
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;
}

/**
 * MapLibre map with OpenFreeMap tiles, an OSM raster fallback and an always-visible
 * "© OpenStreetMap contributors" attribution. The map is keyboard operable (MapLibre handles
 * arrow keys/+/-) and fades/animations are disabled under prefers-reduced-motion.
 */
export function MapView({
  styleUrl = DEFAULT_STYLE_URL,
  fallbackRasterUrl = DEFAULT_FALLBACK_RASTER_URL,
  center = CROATIA_CENTER,
  zoom = CROATIA_ZOOM,
  ariaLabel = 'Karta',
  className,
  onLoad,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const onLoadRef = useRef(onLoad);
  onLoadRef.current = onLoad;
  const [usingFallback, setUsingFallback] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const map = new MapLibreMap({
      container,
      style: styleUrl,
      center,
      zoom,
      attributionControl: false,
      fadeDuration: prefersReducedMotion() ? 0 : 300,
    });
    map.addControl(
      new AttributionControl({ compact: false, customAttribution: OSM_ATTRIBUTION }),
      'bottom-right',
    );
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right');

    let ready = false;
    let fellBack = false;
    const notifyReady = () => {
      if (ready) return;
      ready = true;
      onLoadRef.current?.(map);
    };
    map.on('load', notifyReady);
    map.on('error', (event) => {
      // Tile/source errors carry a sourceId; a style-level failure (no sourceId) before the map
      // was ready means the vector style is unusable: switch to raster tiles once.
      const sourceId = (event as unknown as { sourceId?: string }).sourceId;
      if (ready || fellBack || sourceId) return;
      fellBack = true;
      setUsingFallback(true);
      map.setStyle(rasterFallbackStyle(fallbackRasterUrl));
      map.once('idle', notifyReady);
    });

    return () => {
      map.remove();
    };
    // The map is created once per mount; later prop changes do not recreate it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className={['dt-map', className].filter(Boolean).join(' ')}
      role="region"
      aria-label={ariaLabel}
    >
      <div ref={containerRef} className="dt-map__canvas" />
      <div aria-live="polite">
        {usingFallback ? (
          <p className="dt-map__notice">
            Osnovna vektorska karta nije dostupna; prikazana je pričuvna OpenStreetMap karta.
          </p>
        ) : null}
      </div>
    </div>
  );
}
