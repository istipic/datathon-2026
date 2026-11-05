import type { FeatureCollection } from 'geojson';
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';
import { floodFilter, frontFilter, routeGradient, timeRamp } from './flood';
import type { Coord } from './route';

/** Night Atlas map colours (same values as --na-accent / --na-accent-2 in index.css). */
export const NEAR = '#22D3EE';
export const FAR = '#A78BFA';
export const FRONT = '#CFFAFE';

/** Layers go below the first symbol layer so that street and place labels stay on top. */
export function firstSymbolId(map: MapLibreMap): string | undefined {
  return map.getStyle()?.layers?.find((l) => l.type === 'symbol')?.id;
}

function removeAll(map: MapLibreMap, layers: string[], source: string) {
  for (const id of layers) if (map.getLayer(id)) map.removeLayer(id);
  if (map.getSource(source)) map.removeSource(source);
}

/** Walking-time flood: glow + crisp line + bright front, all driven by a clock in minutes. */
export class FloodLayer {
  private readonly ids = ['flood-glow', 'flood-line', 'flood-front'];
  private clockMin = 0;

  constructor(
    private readonly map: MapLibreMap,
    data: FeatureCollection,
    private readonly maxMin: number,
  ) {
    const before = firstSymbolId(map);
    const ramp = timeRamp(maxMin, NEAR, FAR) as never;
    map.addSource('flood', { type: 'geojson', data });
    map.addLayer(
      {
        id: 'flood-glow',
        type: 'line',
        source: 'flood',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ramp,
          'line-width': ['interpolate', ['linear'], ['zoom'], 11, 4, 16, 16] as never,
          'line-blur': 8,
          'line-opacity': 0.4,
        },
      },
      before,
    );
    map.addLayer(
      {
        id: 'flood-line',
        type: 'line',
        source: 'flood',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ramp,
          'line-width': ['interpolate', ['linear'], ['zoom'], 11, 1.1, 16, 3.5] as never,
          'line-opacity': 0.95,
        },
      },
      before,
    );
    map.addLayer(
      {
        id: 'flood-front',
        type: 'line',
        source: 'flood',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': FRONT,
          'line-width': ['interpolate', ['linear'], ['zoom'], 11, 1.6, 16, 5] as never,
          'line-blur': 1,
          'line-opacity': 0.95,
        },
      },
      before,
    );
    this.setClock(0);
  }

  /** Reveals every street reached up to `min` minutes (the data itself comes from the API). */
  setClock(min: number) {
    this.clockMin = min;
    const m = this.map;
    const all = floodFilter(min) as never;
    if (m.getLayer('flood-glow')) m.setFilter('flood-glow', all);
    if (m.getLayer('flood-line')) m.setFilter('flood-line', all);
    // the front is only visible while the flood is moving
    if (m.getLayer('flood-front')) m.setFilter('flood-front', frontFilter(min) as never);
  }

  /** Rests the front (static final state) or shows it again while animating. */
  setFrontVisible(visible: boolean) {
    if (this.map.getLayer('flood-front'))
      this.map.setPaintProperty('flood-front', 'line-opacity', visible ? 0.95 : 0);
  }

  /** Dims the flood to ground light (used while a route is shown). */
  setDim(dim: boolean) {
    for (const id of ['flood-glow', 'flood-line'])
      if (this.map.getLayer(id))
        this.map.setPaintProperty(
          id,
          'line-opacity',
          id === 'flood-glow' ? (dim ? 0.15 : 0.4) : dim ? 0.45 : 0.95,
        );
  }

  get clock() {
    return this.clockMin;
  }
  get max() {
    return this.maxMin;
  }

  setData(data: FeatureCollection) {
    (this.map.getSource('flood') as GeoJSONSource | undefined)?.setData(data);
  }

  destroy() {
    removeAll(this.map, this.ids, 'flood');
  }
}

/** One route slot: lineMetrics source, a soft trail and the bright line whose gradient draws it. */
export class RouteLayer {
  private readonly ids: string[];

  constructor(
    private readonly map: MapLibreMap,
    private readonly id: string,
  ) {
    this.ids = [`${id}-trail`, `${id}-line`];
    const before = firstSymbolId(map);
    map.addSource(id, {
      type: 'geojson',
      lineMetrics: true,
      data: { type: 'FeatureCollection', features: [] },
    });
    map.addLayer(
      {
        id: `${id}-trail`,
        type: 'line',
        source: id,
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-width': ['interpolate', ['linear'], ['zoom'], 12, 6, 17, 18] as never,
          'line-blur': 6,
          'line-gradient': routeGradient(0, 'rgba(34,211,238,0.35)') as never,
          'line-opacity-transition': { duration: 500, delay: 0 },
        },
      },
      before,
    );
    map.addLayer(
      {
        id: `${id}-line`,
        type: 'line',
        source: id,
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-width': ['interpolate', ['linear'], ['zoom'], 12, 2.5, 17, 6] as never,
          'line-gradient': routeGradient(0, NEAR) as never,
          'line-opacity-transition': { duration: 500, delay: 0 },
        },
      },
      before,
    );
  }

  setCoordinates(coords: Coord[]) {
    (this.map.getSource(this.id) as GeoJSONSource | undefined)?.setData({
      type: 'Feature',
      properties: {},
      geometry: { type: 'LineString', coordinates: coords },
    });
  }

  /** Progress 0..1 of the drawn part: only the gradient stops move, the geometry stays. */
  setProgress(p: number) {
    if (!this.map.getLayer(`${this.id}-line`)) return;
    this.map.setPaintProperty(`${this.id}-line`, 'line-gradient', routeGradient(p, NEAR) as never);
    this.map.setPaintProperty(
      `${this.id}-trail`,
      'line-gradient',
      routeGradient(p, 'rgba(34,211,238,0.35)') as never,
    );
  }

  setOpacity(o: number) {
    for (const id of this.ids)
      if (this.map.getLayer(id)) this.map.setPaintProperty(id, 'line-opacity', o);
  }

  destroy() {
    removeAll(this.map, this.ids, this.id);
  }
}

/** Real building footprints extruded with the tiles' own `render_height` / `render_min_height`. */
export class BuildingsLayer {
  static readonly ID = 'na-buildings';

  constructor(private readonly map: MapLibreMap) {
    if (map.getLayer(BuildingsLayer.ID)) return;
    map.addLayer(
      {
        id: BuildingsLayer.ID,
        type: 'fill-extrusion',
        source: 'openmaptiles',
        'source-layer': 'building',
        minzoom: 14,
        filter: ['!=', ['get', 'hide_3d'], true] as never, // parts of buildings drawn elsewhere
        paint: {
          'fill-extrusion-color': '#2A3446',
          'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 0] as never,
          'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0] as never,
          'fill-extrusion-opacity': 0,
          'fill-extrusion-vertical-gradient': true,
          'fill-extrusion-opacity-transition': { duration: 900, delay: 0 },
        },
      },
      firstSymbolId(map),
    );
  }

  /** Fades the buildings in or out with the native paint transition (constant opacity, not data driven). */
  setVisible(visible: boolean) {
    if (this.map.getLayer(BuildingsLayer.ID))
      this.map.setPaintProperty(BuildingsLayer.ID, 'fill-extrusion-opacity', visible ? 0.82 : 0);
  }

  destroy() {
    if (this.map.getLayer(BuildingsLayer.ID)) this.map.removeLayer(BuildingsLayer.ID);
  }
}
