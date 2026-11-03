/** Legend helpers for the unmet-need choropleth (no map library imported here). */

/** Sequential 5-class ramp (single hue, light to dark) + "no unmet need". */
export const NEED_COLORS = ['#CCE7E2', '#8FCFC4', '#4FB0A3', '#1F8579', '#0A5750'];
export const NO_NEED_COLOR = '#E2E8F0';

/** Grad Zagreb: [west, south], [east, north]. */
export const ZAGREB_BOUNDS: [[number, number], [number, number]] = [
  [15.77, 45.61],
  [16.24, 45.97],
];

export interface LegendClass {
  color: string;
  from: number;
  to: number | null;
}

/** Class intervals from quantile breaks (unmet > 0): [0,b1], (b1,b2], ..., (b4, max]. */
export function legendClasses(breaks: number[], max: number): LegendClass[] {
  const edges = [...new Set(breaks.map((b) => Math.round(b * 10) / 10))]
    .filter((b) => b > 0)
    .sort((a, b) => a - b);
  const classes: LegendClass[] = [];
  let from = 0;
  edges.forEach((edge, i) => {
    classes.push({ color: NEED_COLORS[i] as string, from, to: edge });
    from = edge;
  });
  classes.push({ color: NEED_COLORS[edges.length] as string, from, to: max > from ? max : null });
  return classes;
}
