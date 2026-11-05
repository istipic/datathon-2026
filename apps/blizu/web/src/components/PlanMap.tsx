import { MapView } from '@dt/ui';
import { Marker, Popup, type GeoJSONSource, type Map as MapLibreMap } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import { useEffect, useRef, useState } from 'react';
import { clock, prefersReducedMotion } from '../lib/anim/clock';
import { easeInOutCubic } from '../lib/anim/easing';
import { blendExpression, columnHeightExpression } from '../lib/anim/flood';
import { firstSymbolId } from '../lib/anim/layers';
import { createTimeline, play, throttleApply, type PlayHandle } from '../lib/anim/timeline';
import { ZAGREB_BOUNDS } from '../lib/legend';
import { formatInt } from '../lib/labels';
import { buildColumns, columnScale, needFillExpression, type ColumnProps } from '../lib/planner3d';
import type { NeedCollection, OptimiseResult, OptimiseSite } from '../lib/types';
import { Icon } from './ui';

/** Duration of the before -> after animation of the columns (the headline counts for the same time). */
export const COLUMNS_MS = 900;
const PITCH = 52;

interface Props {
  need: NeedCollection | undefined;
  optimise?: OptimiseResult;
  sites: OptimiseSite[];
  /** Centre the first view on this address (set when the planner is opened from a result card). */
  focus?: { lon: number; lat: number } | null;
}

function siteElement(site: OptimiseSite, i: number, animate: boolean): HTMLElement {
  // outer element is positioned by MapLibre; the inner one carries the drop-in animation
  const outer = document.createElement('div');
  const el = document.createElement('div');
  el.className = 'blizu-site' + (animate ? ' na-pop' : '');
  if (animate) el.style.animationDelay = `${i * 140}ms`;
  el.setAttribute('role', 'img');
  el.setAttribute(
    'aria-label',
    `Predložena lokacija ${i + 1}${site.street ? `, ${site.street}` : ''}: ${site.newly_covered} osoba`,
  );
  el.textContent = `+${site.newly_covered.toLocaleString('hr-HR')} osoba`;
  outer.append(el);
  if (animate) {
    const ring = document.createElement('span');
    ring.className = 'na-shockwave'; // decorative
    ring.style.animationDelay = `${i * 140}ms`;
    ring.setAttribute('aria-hidden', 'true');
    outer.append(ring);
  }
  return outer;
}

/** Planner map: unmet need as columns that sink from "before" to "after", plus the suggested sites. */
export function PlanMap({ need, optimise, sites, focus }: Props) {
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [flat, setFlat] = useState(false);
  const markers = useRef<Marker[]>([]);
  const shown = useRef<Map<string, number>>(new Map()); // heights currently on screen (need units)
  const player = useRef<PlayHandle | null>(null);
  const scale = useRef(0);

  // first view
  const fitted = useRef(false);
  useEffect(() => {
    if (!map || fitted.current) return;
    fitted.current = true;
    const reduced = prefersReducedMotion();
    if (focus) {
      map.jumpTo({ center: [focus.lon, focus.lat], zoom: 12.2, pitch: PITCH, bearing: -12 });
    } else {
      map.fitBounds(ZAGREB_BOUNDS, { padding: 40, duration: 0 });
      if (reduced) map.jumpTo({ pitch: PITCH });
      else map.easeTo({ pitch: PITCH, bearing: -12, duration: 1400, essential: false });
    }
  }, [map, focus]);

  // columns
  useEffect(() => {
    if (!map || !need) return;
    const breaks = need.summary.breaks;
    const values = need.features.map((f) => f.properties.unmet);
    const setExpressions = (p: number) => {
      if (!map.getLayer('need-columns')) return;
      map.setPaintProperty(
        'need-columns',
        'fill-extrusion-height',
        columnHeightExpression(p, scale.current, 'need_before', 'need_after') as never,
      );
      map.setPaintProperty(
        'need-columns',
        'fill-extrusion-color',
        needFillExpression(breaks, blendExpression(p, 'need_before', 'need_after')) as never,
      );
    };
    const apply = () => {
      player.current?.cancel();
      const cells = optimise?.cells;
      const data = buildColumns(need, cells, cells ? shown.current : undefined);
      scale.current = columnScale([
        ...values,
        ...data.features.map((f) => f.properties.need_after),
        ...data.features.map((f) => f.properties.need_before),
      ]);
      const source = map.getSource('need') as GeoJSONSource | undefined;
      if (source) source.setData(data as unknown as FeatureCollection);
      else {
        map.addSource('need', { type: 'geojson', data: data as unknown as FeatureCollection });
        const before = firstSymbolId(map);
        map.addLayer(
          {
            id: 'need-columns',
            type: 'fill-extrusion',
            source: 'need',
            paint: {
              'fill-extrusion-height': 0,
              'fill-extrusion-color': NEED_PLACEHOLDER,
              'fill-extrusion-opacity': 0.92,
              'fill-extrusion-vertical-gradient': true,
            },
          },
          before,
        );
      }
      const finish = () => {
        const next = new Map<string, number>();
        for (const f of data.features) next.set(f.properties.grd_id, f.properties.need_after);
        shown.current = next;
      };
      if (!cells) {
        shown.current = new Map();
        setExpressions(0);
        return;
      }
      const tl = createTimeline([
        {
          at: 0,
          duration: COLUMNS_MS,
          ease: easeInOutCubic,
          apply: throttleApply(setExpressions),
        },
      ]);
      player.current = play(clock, tl, { reduced: prefersReducedMotion(), onDone: finish });
    };
    if (map.isStyleLoaded()) apply();
    else map.once('idle', apply);
    return () => player.current?.cancel();
  }, [map, need, optimise]);

  // hover tooltip with the real numbers of the cell under the pointer
  useEffect(() => {
    if (!map) return;
    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 12 });
    const onMove = (e: {
      point: { x: number; y: number };
      lngLat: { lng: number; lat: number };
    }) => {
      if (!map.getLayer('need-columns')) return;
      const hit = map.queryRenderedFeatures([e.point.x, e.point.y], {
        layers: ['need-columns'],
      })[0];
      if (!hit) {
        popup.remove();
        return;
      }
      const p = hit.properties as unknown as ColumnProps;
      const root = document.createElement('div');
      const line1 = document.createElement('strong');
      line1.textContent = `Potreba ${formatInt(p.need_before)}`;
      if (optimise) line1.textContent += ` → ${formatInt(p.need_after)}`;
      root.append(line1);
      if (optimise) {
        const line2 = document.createElement('div');
        line2.textContent = `Osoba izvan dosega: ${formatInt(p.people_before)} → ${formatInt(p.people_after)}`;
        root.append(line2);
      }
      popup.setLngLat([e.lngLat.lng, e.lngLat.lat]).setDOMContent(root).addTo(map);
    };
    map.on('mousemove', onMove);
    map.getCanvas().addEventListener('mouseleave', () => popup.remove());
    return () => {
      map.off('mousemove', onMove);
      popup.remove();
    };
  }, [map, optimise]);

  // suggested sites: drop in with a shockwave
  useEffect(() => {
    if (!map) return;
    markers.current.forEach((m) => m.remove());
    const animate = !prefersReducedMotion();
    markers.current = sites.map((site, i) =>
      new Marker({ element: siteElement(site, i, animate) })
        .setLngLat([site.lon, site.lat])
        .addTo(map),
    );
    return () => {
      markers.current.forEach((m) => m.remove());
      markers.current = [];
    };
  }, [map, sites]);

  function togglePitch() {
    if (!map) return;
    const next = !flat;
    setFlat(next);
    const target = { pitch: next ? 0 : PITCH, bearing: next ? 0 : -12 };
    if (prefersReducedMotion()) map.jumpTo(target);
    else map.easeTo({ ...target, duration: 700, essential: false });
  }

  return (
    <>
      <MapView
        ariaLabel="Karta nezadovoljene potrebe po ćelijama od 1 km"
        styleUrl="https://tiles.openfreemap.org/styles/liberty"
        navigationControl={false}
        onLoad={(m) => {
          setMap(m);
          if (import.meta.env.DEV)
            (window as unknown as { __blizuMap?: MapLibreMap }).__blizuMap = m;
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
          data-tip={flat ? 'Stupci (3D)' : 'Pogled odozgo'}
          aria-label="Pogled odozgo"
          aria-pressed={flat}
          disabled={!map}
          onClick={togglePitch}
        >
          <Icon name="cube" />
        </button>
      </div>
    </>
  );
}

/** Colour until the first expression is applied (the dim "no need" tone). */
const NEED_PLACEHOLDER = '#1A222D';
