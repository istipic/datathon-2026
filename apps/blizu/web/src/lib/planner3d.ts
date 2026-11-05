import type { Feature, FeatureCollection, Polygon } from 'geojson';
import { NEED_COLORS, NO_NEED_COLOR } from './legend';
import type { NeedCollection, OptimiseCell } from './types';

export interface ColumnProps {
  grd_id: string;
  /** Height basis before / after the suggested sites, in the units of `/plan/need` `unmet`. */
  need_before: number;
  need_after: number;
  /** People of the target group beyond the limit (sums to `total_newly_covered` over all cells). */
  people_before: number;
  people_after: number;
}

/**
 * Shrinks a polygon towards its centroid so neighbouring columns do not merge into one slab.
 * // decorative: the footprint is only drawn smaller, heights and values are untouched.
 */
export function insetPolygon(polygon: Polygon, factor = 0.78): Polygon {
  const ring = polygon.coordinates[0] ?? [];
  if (ring.length === 0) return polygon;
  const pts = ring.slice(0, -1);
  const cx = pts.reduce((s, p) => s + (p[0] as number), 0) / pts.length;
  const cy = pts.reduce((s, p) => s + (p[1] as number), 0) / pts.length;
  const shrink = (p: number[]) => [
    cx + ((p[0] as number) - cx) * factor,
    cy + ((p[1] as number) - cy) * factor,
  ];
  return { type: 'Polygon', coordinates: [ring.map(shrink)] };
}

/**
 * Column features: the real cell polygons of `/plan/need` joined (by `grd_id` = `cell_id`) with the
 * before/after values of `/plan/optimise`. Without an optimise result after = before.
 * `current` holds the heights already on screen, so a changed `k` replays from the current state.
 */
export function buildColumns(
  need: NeedCollection,
  cells?: OptimiseCell[],
  current?: ReadonlyMap<string, number>,
): FeatureCollection<Polygon, ColumnProps> {
  const byId = new Map((cells ?? []).map((c) => [c.cell_id, c]));
  const features: Feature<Polygon, ColumnProps>[] = need.features.map((f) => {
    const cell = byId.get(f.properties.grd_id);
    const base = f.properties.unmet;
    const before = current?.get(f.properties.grd_id) ?? cell?.need_before ?? base;
    return {
      type: 'Feature',
      geometry: insetPolygon(f.geometry),
      properties: {
        grd_id: f.properties.grd_id,
        need_before: before,
        need_after: cell?.need_after ?? before,
        people_before: cell?.unmet_before ?? 0,
        people_after: cell?.unmet_after ?? 0,
      },
    };
  });
  return { type: 'FeatureCollection', features };
}

/** Metres of column height per unit of need, so the tallest column is `maxHeightM` high. */
export function columnScale(values: number[], maxHeightM = 2600): number {
  const max = Math.max(0, ...values);
  return max > 0 ? maxHeightM / max : 0;
}

/** Colour of a value from the API's real quantile breaks (same classes as the legend). */
export function needFillExpression(breaks: number[], value: unknown[]): unknown[] {
  const edges = [...new Set(breaks.map((b) => Math.round(b * 10) / 10))]
    .filter((b) => b > 0)
    .sort((a, b) => a - b);
  if (edges.length === 0) return ['case', ['<=', value, 0], NO_NEED_COLOR, NEED_COLORS[2]];
  return [
    'case',
    ['<=', value, 0],
    NO_NEED_COLOR,
    ['step', value, NEED_COLORS[0], ...edges.flatMap((e, i) => [e, NEED_COLORS[i + 1]])],
  ];
}

/** Rows of the accessible table: the cells that gain the most, with real before/after people. */
export function topChangedCells(cells: OptimiseCell[], n = 5): OptimiseCell[] {
  return [...cells]
    .filter((c) => c.unmet_before - c.unmet_after > 0)
    .sort((a, b) => b.unmet_before - b.unmet_after - (a.unmet_before - a.unmet_after))
    .slice(0, n);
}
