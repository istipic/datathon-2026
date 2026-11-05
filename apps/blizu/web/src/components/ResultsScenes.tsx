import { useQuery } from '@tanstack/react-query';
import type { LngLatBoundsLike, Map as MapLibreMap, Marker as MarkerType } from 'maplibre-gl';
import { Marker, LngLatBounds } from 'maplibre-gl';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { api } from '../lib/api';
import { useIsochrone } from '../lib/useIsochrone';
import { moveCamera, orbitBearing, presetTarget } from '../lib/anim/camera';
import { clock, prefersReducedMotion } from '../lib/anim/clock';
import { easeInOutCubic } from '../lib/anim/easing';
import { floodClock } from '../lib/anim/flood';
import { BuildingsLayer, FloodLayer, RouteLayer } from '../lib/anim/layers';
import {
  buildRoute,
  positionAt,
  walkProgress,
  type Coord,
  type RouteGeometry,
} from '../lib/anim/route';
import { SCENES, SCENE_LABEL, type ActiveScene } from '../lib/anim/scene';
import { createTimeline, play, throttleApply, type PlayHandle } from '../lib/anim/timeline';
import { CATEGORY_SHORT, countText, formatMinutes, minutesWord } from '../lib/labels';
import type { CategoryId, IsochroneFacility, IsochroneResult, PersonaId } from '../lib/types';
import { CategoryIcon } from './CategoryIcon';
import { Icon } from './ui';

/** Screen seconds of the first flood: 15 minutes of walking in 2.5 s. */
const FLOOD_MS = 2500;
const CHIPS = [5, 10, 15];
/** The persona's real walking speed is multiplied by this constant (shown in the UI as "ubrzano ×30"). */
export const TIMELAPSE = 30;
const DRAW_MS = 1400;

interface Props {
  map: MapLibreMap;
  origin: { lon: number; lat: number };
  persona: PersonaId;
  scene: ActiveScene;
  onScene: (scene: ActiveScene) => void;
  /** Category whose route is shown in the "Put do…" scene. */
  category: CategoryId | null;
  /** The vector style failed: the raster fallback has no buildings, so 3D is off. */
  fallback: boolean;
}

/** Camera padding that keeps the subject clear of the floating bars (and of the bottom sheet on phones). */
function viewPadding(bottom: number) {
  const phone =
    typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 860px)').matches;
  return phone
    ? { top: 70, bottom: 470, left: 24, right: 64 }
    : { top: 90, bottom, left: 70, right: 90 };
}

function whenReady(map: MapLibreMap, fn: () => void): () => void {
  if (map.isStyleLoaded()) {
    fn();
    return () => undefined;
  }
  const handler = () => fn();
  map.once('idle', handler);
  return () => map.off('idle', handler);
}

function boundsOf(iso: IsochroneResult): LngLatBounds {
  const b = new LngLatBounds([iso.origin.lon, iso.origin.lat], [iso.origin.lon, iso.origin.lat]);
  for (const f of iso.buckets.features)
    for (const line of f.geometry.coordinates) for (const c of line) b.extend(c as Coord);
  return b;
}

const ICON_HTML = new Map<CategoryId, string>();
/** Icon markup is rendered once per category (not once per marker): 100+ markers would block the main thread. */
function iconHtml(category: CategoryId): string {
  let html = ICON_HTML.get(category);
  if (html === undefined) {
    html = renderToStaticMarkup(<CategoryIcon category={category} size={12} />);
    ICON_HTML.set(category, html);
  }
  return html;
}

function facilityElement(f: IsochroneFacility): HTMLElement {
  // outer element is positioned by MapLibre (it owns its transform); the inner one pops in
  const outer = document.createElement('div');
  outer.style.display = 'none';
  const el = document.createElement('div');
  el.className = 'blizu-marker na-reach';
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', `${CATEGORY_SHORT[f.category]}: ${f.name}, ${formatMinutes(f.t)}`);
  el.title = `${f.name} · ${formatMinutes(f.t)}`;
  el.innerHTML = iconHtml(f.category);
  outer.append(el);
  return outer;
}

function summarise(
  iso: IsochroneResult,
  minute: number,
): { text: string; items: IsochroneFacility[] } {
  const items = iso.facilities.filter((f) => f.t <= minute + 1e-9);
  // at the API's own thresholds the API's counts are used verbatim
  const fromApi = Number.isInteger(minute) ? iso.counts[String(minute)] : undefined;
  const per = new Map<CategoryId, number>();
  if (fromApi) {
    for (const [c, n] of Object.entries(fromApi)) per.set(c as CategoryId, n as number);
  } else {
    for (const f of items) per.set(f.category, (per.get(f.category) ?? 0) + 1);
  }
  const parts = [...per.entries()].map(([c, n]) => countText(c, n));
  const label = minutesWord(Math.round(minute));
  return {
    text: parts.length > 0 ? `U dosegu ${label}: ${parts.join(', ')}` : `U dosegu ${label}: ništa`,
    items,
  };
}

/** Scene switcher, flood, route and 3D controllers on top of the results map. */
export function ResultsScenes({ map, origin, persona, scene, onScene, category, fallback }: Props) {
  const iso = useIsochrone(origin.lat, origin.lon, persona);
  const routeQuery = useQuery({
    queryKey: ['route', origin.lat, origin.lon, persona, category],
    queryFn: ({ signal }) =>
      api.route(origin.lat, origin.lon, persona, category as CategoryId, signal),
    enabled: scene === 'put' && category !== null,
    staleTime: 10 * 60_000,
    retry: false,
  });

  const flood = useRef<FloodLayer | null>(null);
  // facility markers are created when the front first reaches them (100+ DOM markers upfront block the main thread)
  const markers = useRef<{ f: IsochroneFacility; t: number; marker: MarkerType | null }[]>([]);
  const player = useRef<PlayHandle | null>(null);
  const slider = useRef<HTMLInputElement | null>(null);
  const sceneRef = useRef(scene);
  sceneRef.current = scene;
  const [summary, setSummary] = useState<{ text: string; items: IsochroneFacility[] } | null>(null);
  const [rest, setRest] = useState('');
  const [clockMin, setClockMin] = useState(15); // only changes at rest or by user input, never per frame

  // ------------------------------------------------------------------ on-screen detection
  useEffect(() => {
    const el = map.getContainer();
    if (typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver((entries) =>
      clock.setOnScreen(entries.some((e) => e.isIntersecting)),
    );
    io.observe(el);
    return () => {
      io.disconnect();
      clock.setOnScreen(true);
    };
  }, [map]);

  // ------------------------------------------------------------------ flood
  /** Moves the flood to `min` minutes: filters, markers, slider and counter (text changes rarely). */
  const applyClock = useCallback(
    (min: number, data: IsochroneResult) => {
      flood.current?.setClock(min);
      for (const m of markers.current) {
        const reached = m.t <= min + 1e-9;
        if (reached) {
          if (!m.marker) {
            const el = facilityElement(m.f);
            el.style.visibility = sceneRef.current === 'put' ? 'hidden' : 'visible';
            m.marker = new Marker({ element: el }).setLngLat([m.f.lon, m.f.lat]).addTo(map);
            el.style.display = '';
            if (!prefersReducedMotion()) el.firstElementChild?.classList.add('na-pop');
          } else if (m.marker.getElement().style.display === 'none') {
            const el = m.marker.getElement();
            el.style.display = ''; // display:none -> '' restarts the CSS animation by itself
            if (!prefersReducedMotion()) el.firstElementChild?.classList.add('na-pop');
          }
        } else if (m.marker && m.marker.getElement().style.display !== 'none') {
          m.marker.getElement().style.display = 'none';
        }
      }
      if (slider.current) {
        slider.current.value = String(min);
        slider.current.setAttribute('aria-valuetext', minutesWord(Math.round(min)));
      }
      const next = summarise(data, Math.floor(min));
      setSummary((prev) => (prev && prev.text === next.text ? prev : next));
    },
    [map],
  );

  const playFlood = useCallback(
    (data: IsochroneResult, from: number, to: number, ms: number) => {
      player.current?.cancel();
      const layer = flood.current;
      if (!layer) return;
      const reduced = prefersReducedMotion();
      layer.setFrontVisible(!reduced);
      const tl = createTimeline([
        {
          at: 0,
          duration: ms,
          ease: easeInOutCubic,
          apply: throttleApply((p) => {
            const span = to - from;
            applyClock(from + floodClock(p * ms, ms, 1) * span, data);
          }),
        },
      ]);
      player.current = play(clock, tl, {
        reduced,
        onDone: () => {
          layer.setFrontVisible(false);
          setClockMin(to);
          const final = summarise(data, Math.floor(to));
          setRest(final.text);
        },
      });
    },
    [applyClock],
  );

  useEffect(() => {
    const data = iso.data;
    if (!data) return;
    let cancelled = false;
    let layer: FloodLayer | null = null;
    const markerList: { f: IsochroneFacility; t: number; marker: MarkerType | null }[] =
      data.facilities.map((f) => ({ f, t: f.t, marker: null }));
    const dispose = whenReady(map, () => {
      if (cancelled) return;
      layer = new FloodLayer(map, data.buckets, data.max_min);
      flood.current = layer;
      markers.current = markerList;
      if (sceneRef.current !== 'put') {
        const reduced = prefersReducedMotion();
        const box = boundsOf(data);
        map.fitBounds(box as LngLatBoundsLike, {
          padding: viewPadding(150),
          maxZoom: 17,
          duration: reduced ? 0 : 900,
          essential: false,
        });
        playFlood(data, 0, data.max_min, FLOOD_MS);
      } else {
        applyClock(data.max_min, data);
        layer.setFrontVisible(false);
        layer.setDim(true);
      }
    });
    return () => {
      cancelled = true;
      dispose();
      player.current?.cancel();
      layer?.destroy();
      flood.current = null;
      markerList.forEach((m) => m.marker?.remove());
      markers.current = [];
    };
  }, [iso.data, map, applyClock, playFlood]);

  const goTo = useCallback(
    (min: number) => {
      const data = iso.data;
      if (!data) return;
      player.current?.cancel();
      const reduced = prefersReducedMotion();
      const from = flood.current?.clock ?? min;
      if (reduced || Math.abs(from - min) < 0.01) {
        flood.current?.setFrontVisible(false);
        applyClock(min, data);
        setClockMin(min);
        setRest(summarise(data, Math.floor(min)).text);
      } else {
        playFlood(data, from, min, 650);
      }
    },
    [iso.data, applyClock, playFlood],
  );

  // the flood's facility markers belong to the flood scenes; the route scene shows the nearest ones
  useEffect(() => {
    for (const m of markers.current)
      if (m.marker) m.marker.getElement().style.visibility = scene === 'put' ? 'hidden' : 'visible';
  }, [scene, iso.data]);

  // ------------------------------------------------------------------ route
  const slots = useRef<{ layers: [RouteLayer, RouteLayer]; active: 0 | 1 } | null>(null);
  const dot = useRef<MarkerType | null>(null);
  const routePlayer = useRef<PlayHandle | null>(null);
  const [routeInfo, setRouteInfo] = useState<{
    name: string;
    minutes: number;
    meters: number;
  } | null>(null);
  const routeData = routeQuery.data;

  useEffect(() => {
    let cancelled = false;
    const dispose = whenReady(map, () => {
      if (cancelled) return;
      slots.current = {
        layers: [new RouteLayer(map, 'route-a'), new RouteLayer(map, 'route-b')],
        active: 0,
      };
      const el = document.createElement('div');
      el.className = 'na-dot';
      el.style.display = 'none';
      el.setAttribute('aria-hidden', 'true'); // decorative: the route itself is described in the panel
      dot.current = new Marker({ element: el }).setLngLat([origin.lon, origin.lat]).addTo(map);
    });
    return () => {
      cancelled = true;
      dispose();
      routePlayer.current?.cancel();
      slots.current?.layers.forEach((l) => l.destroy());
      slots.current = null;
      dot.current?.remove();
      dot.current = null;
    };
  }, [map, origin.lon, origin.lat]);

  const route: RouteGeometry | null = useMemo(
    () => (routeData ? buildRoute(routeData.coordinates) : null),
    [routeData],
  );

  const playRoute = useCallback(() => {
    const s = slots.current;
    if (!s || !routeData || !route) return;
    routePlayer.current?.cancel();
    const reduced = prefersReducedMotion();
    // morph: the other slot draws the new route while the previous one fades out
    const next = (1 - s.active) as 0 | 1;
    const fresh = s.layers[next];
    const old = s.layers[s.active];
    old.setOpacity(0);
    fresh.setCoordinates(routeData.coordinates);
    fresh.setOpacity(1);
    fresh.setProgress(0);
    s.active = next;
    setRouteInfo({
      name: routeData.facility.name,
      minutes: routeData.minutes,
      meters: routeData.distance_m,
    });

    const bounds = new LngLatBounds(
      routeData.coordinates[0] as Coord,
      routeData.coordinates[0] as Coord,
    );
    routeData.coordinates.forEach((c) => bounds.extend(c));
    map.fitBounds(bounds, {
      padding: viewPadding(170),
      maxZoom: 17,
      duration: reduced ? 0 : 1100,
      essential: false,
    });

    const dotEl = dot.current?.getElement();
    const walkMs = (route.length / routeData.speed_mps / TIMELAPSE) * 1000;
    if (dotEl) dotEl.style.display = reduced ? 'none' : '';
    const tl = createTimeline([
      {
        at: 0,
        duration: DRAW_MS,
        ease: easeInOutCubic,
        apply: throttleApply((p) => fresh.setProgress(p)),
      },
      {
        at: DRAW_MS * 0.6,
        duration: Math.max(1, walkMs),
        apply: throttleApply((p) => {
          const at = positionAt(
            route,
            walkProgress(route, p * walkMs, routeData.speed_mps, TIMELAPSE),
          );
          dot.current?.setLngLat(at);
        }),
      },
    ]);
    routePlayer.current = play(clock, tl, { reduced });
    if (reduced) fresh.setProgress(1);
  }, [map, routeData, route]);

  useEffect(() => {
    if (scene !== 'put') {
      routePlayer.current?.cancel();
      slots.current?.layers.forEach((l) => l.setOpacity(0));
      const el = dot.current?.getElement();
      if (el) el.style.display = 'none';
      return;
    }
    if (routeData) return whenReady(map, playRoute);
  }, [scene, routeData, map, playRoute]);

  // ------------------------------------------------------------------ flood dim, 3D
  useEffect(() => {
    flood.current?.setDim(scene === 'put');
  }, [scene, iso.data]);

  const buildings = useRef<BuildingsLayer | null>(null);
  const [threeDNote, setThreeDNote] = useState('');
  useEffect(() => {
    if (scene !== '3d') return;
    if (fallback) {
      setThreeDNote('3D nije dostupan jer se koristi pričuvna karta.');
      return;
    }
    setThreeDNote('');
    let cancelled = false;
    let unsubscribe: (() => void) | null = null;
    const stop = () => {
      unsubscribe?.();
      unsubscribe = null;
    };
    const dispose = whenReady(map, () => {
      if (cancelled) return;
      buildings.current ??= new BuildingsLayer(map);
      buildings.current.setVisible(true);
      const reduced = prefersReducedMotion();
      moveCamera(map, presetTarget('orbit', [origin.lon, origin.lat], map.getBearing()), {
        reduced,
        duration: 1800,
      });
      if (reduced) return;
      const startBearing = map.getBearing();
      let elapsed = 0;
      let acc = 0;
      // orbit only after the fly-in; any user input stops it
      const startAt = performance.now() + 1900;
      unsubscribe = clock.subscribe((now, dt) => {
        if (performance.now() < startAt) return;
        elapsed += dt;
        acc += dt;
        if (acc < 33) return;
        acc = 0;
        map.setBearing(orbitBearing(startBearing, elapsed));
      });
      for (const ev of ['dragstart', 'mousedown', 'touchstart', 'wheel'] as const)
        map.once(ev, stop);
    });
    return () => {
      cancelled = true;
      dispose();
      stop();
      buildings.current?.setVisible(false);
      if (map.getPitch() > 0 && sceneRef.current !== '3d') {
        moveCamera(map, presetTarget('street', [map.getCenter().lng, map.getCenter().lat], 0), {
          reduced: prefersReducedMotion(),
          small: true,
          duration: 700,
        });
      }
    };
  }, [scene, fallback, map, origin.lon, origin.lat]);

  useEffect(
    () => () => {
      buildings.current?.destroy();
      buildings.current = null;
    },
    [map],
  );

  // ------------------------------------------------------------------ UI
  const data = iso.data;
  const replay = () => {
    if (scene === 'put') playRoute();
    else if (data) playFlood(data, 0, data.max_min, FLOOD_MS);
  };

  return (
    <>
      <div className="na-pillbar na-scenebar" role="group" aria-label="Prikaz na karti">
        {SCENES.map((s) => (
          <button
            key={s}
            type="button"
            className="na-chip"
            aria-pressed={scene === s}
            disabled={s === '3d' && fallback}
            title={
              s === '3d' && fallback ? '3D nije dostupan jer se koristi pričuvna karta.' : undefined
            }
            onClick={() => onScene(s)}
          >
            {s === '3d' ? <Icon name="cube" size={14} /> : null}
            {SCENE_LABEL[s]}
          </button>
        ))}
      </div>

      {scene !== 'put' ? (
        <section
          className="na-pillbar na-timebar"
          aria-label="Doseg pješice"
          data-testid="reach-bar"
        >
          {data ? (
            <>
              <div className="na-timebar__row">
                <button
                  type="button"
                  className="na-iconbtn"
                  aria-label="Ponovi animaciju dosega"
                  onClick={replay}
                >
                  <Icon name="replay" size={18} />
                </button>
                <label htmlFor="reach-slider" className="dt-sr-only">
                  Minute hoda
                </label>
                <input
                  id="reach-slider"
                  ref={slider}
                  type="range"
                  className="na-range"
                  style={{ flex: '1 1 8rem', minWidth: '8rem' }}
                  min={0}
                  max={data.max_min}
                  step={0.25}
                  defaultValue={data.max_min}
                  aria-valuetext={minutesWord(clockMin)}
                  onChange={(e) => goTo(Number(e.target.value))}
                />
                {CHIPS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className="na-chip"
                    aria-pressed={Math.round(clockMin) === c}
                    onClick={() => goTo(c)}
                  >
                    {c} min
                  </button>
                ))}
              </div>
              <p className="na-counter" data-testid="reach-counter">
                {summary?.text ?? rest}
              </p>
              <p className="dt-sr-only" aria-live="polite" data-testid="reach-live">
                {rest}
              </p>
              {summary && summary.items.length > 0 ? (
                <details className="text-sm">
                  <summary className="na-muted cursor-pointer">
                    Popis objekata u dosegu ({summary.items.length})
                  </summary>
                  <ul className="m-0 mt-2 grid max-h-40 list-none gap-1 overflow-auto p-0">
                    {summary.items.map((f) => (
                      <li key={f.id}>
                        <span className="na-muted">{CATEGORY_SHORT[f.category]}</span> {f.name} ·{' '}
                        <span className="dt-num">{formatMinutes(f.t)}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
              {scene === '3d' && threeDNote ? (
                <p className="na-muted text-xs">{threeDNote}</p>
              ) : null}
            </>
          ) : iso.isError ? null : (
            <p className="na-muted text-sm" role="status">
              Računam doseg…
            </p>
          )}
        </section>
      ) : (
        <section
          className="na-pillbar na-timebar"
          aria-label="Put do objekta"
          data-testid="route-bar"
        >
          {category === null ? (
            <p className="na-counter">Odaberi uslugu u popisu da vidiš put do nje.</p>
          ) : routeQuery.isPending ? (
            <p className="na-muted text-sm" role="status">
              Tražim put…
            </p>
          ) : routeQuery.isError ? (
            <p className="na-counter" role="alert">
              {routeQuery.error instanceof Error ? routeQuery.error.message : 'Put nije dostupan.'}
            </p>
          ) : routeInfo ? (
            <div className="na-timebar__row">
              <button type="button" className="na-iconbtn" aria-label="Ponovi put" onClick={replay}>
                <Icon name="replay" size={18} />
              </button>
              <p className="na-counter" data-testid="route-summary" style={{ margin: 0 }}>
                {routeInfo.name} ·{' '}
                <span className="dt-num">
                  {formatMinutes(routeInfo.minutes)}, {Math.round(routeInfo.meters)} m
                </span>
              </p>
              <span
                className="na-chip"
                title="Točka hoda stvarnom brzinom osobe, samo je sat ubrzan"
              >
                <Icon name="walk" size={14} /> ubrzano ×{TIMELAPSE}
              </span>
            </div>
          ) : null}
        </section>
      )}

      {iso.isError ? (
        <div className="na-glass na-maperr" role="alert">
          <p style={{ margin: 0, fontWeight: 600 }}>Doseg pješice trenutno nije dostupan.</p>
          <p className="na-muted text-sm">
            {iso.error instanceof Error ? iso.error.message : 'Pokušajte ponovno.'} Popis usluga u
            lijevom izborniku i dalje vrijedi.
          </p>
          <button type="button" className="na-btn na-btn--sm" onClick={() => void iso.refetch()}>
            Pokušaj ponovno
          </button>
        </div>
      ) : null}
    </>
  );
}
