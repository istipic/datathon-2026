import { act, cleanup, render, screen } from '@testing-library/react';
import { MapView, OSM_ATTRIBUTION, rasterFallbackStyle } from './MapView';

// jsdom has no WebGL, so maplibre-gl is replaced by a recording fake.
type Handler = (event?: unknown) => void;
interface FakeMapInstance {
  options: Record<string, unknown>;
  handlers: Record<string, Handler[]>;
  controls: { control: { kind: string; options?: Record<string, unknown> }; position: string }[];
  styles: unknown[];
  removed: boolean;
  emit: (type: string, event?: unknown) => void;
}
const { instances } = vi.hoisted(() => ({ instances: [] as FakeMapInstance[] }));

vi.mock('maplibre-gl', () => {
  class FakeMap implements FakeMapInstance {
    handlers: Record<string, Handler[]> = {};
    controls: FakeMapInstance['controls'] = [];
    styles: unknown[] = [];
    removed = false;
    constructor(public options: Record<string, unknown>) {
      instances.push(this);
    }
    on(type: string, fn: Handler) {
      (this.handlers[type] ??= []).push(fn);
      return this;
    }
    once(type: string, fn: Handler) {
      const wrapper: Handler = (e) => {
        this.handlers[type] = (this.handlers[type] ?? []).filter((h) => h !== wrapper);
        fn(e);
      };
      return this.on(type, wrapper);
    }
    addControl(control: FakeMapInstance['controls'][number]['control'], position: string) {
      this.controls.push({ control, position });
    }
    setStyle(style: unknown) {
      this.styles.push(style);
    }
    remove() {
      this.removed = true;
    }
    emit(type: string, event?: unknown) {
      for (const h of [...(this.handlers[type] ?? [])]) h(event);
    }
  }
  const setWorkerUrl = vi.fn();
  class AttributionControl {
    kind = 'attribution';
    constructor(public options: Record<string, unknown>) {}
  }
  class NavigationControl {
    kind = 'navigation';
    constructor(public options: Record<string, unknown>) {}
  }
  return { Map: FakeMap, AttributionControl, NavigationControl, setWorkerUrl };
});

beforeEach(() => {
  instances.length = 0;
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('MapView', () => {
  it('creates a map with the OpenFreeMap style, centred on Croatia', () => {
    render(<MapView />);
    expect(instances).toHaveLength(1);
    const map = instances[0]!;
    expect(map.options.style).toBe('https://tiles.openfreemap.org/styles/liberty');
    expect(map.options.center).toEqual([16.4, 44.5]);
    expect(map.options.zoom).toBe(6.2);
    expect(map.options.container).toBeInstanceOf(HTMLElement);
  });

  it('always adds the "© OpenStreetMap contributors" attribution', () => {
    render(<MapView />);
    const map = instances[0]!;
    expect(map.options.attributionControl).toBe(false); // replaced by our own, non-compact one
    const attribution = map.controls.find((c) => c.control.kind === 'attribution');
    expect(attribution?.control.options).toEqual({
      compact: false,
      customAttribution: OSM_ATTRIBUTION,
    });
    expect(OSM_ATTRIBUTION).toBe('© OpenStreetMap contributors');
    expect(map.controls.some((c) => c.control.kind === 'navigation')).toBe(true);
  });

  it('is a labelled region', () => {
    render(<MapView ariaLabel="Karta ljekarni" />);
    expect(screen.getByRole('region', { name: 'Karta ljekarni' })).toBeTruthy();
  });

  it('honours a custom style URL and center/zoom', () => {
    render(<MapView styleUrl="https://example.org/style.json" center={[15, 45]} zoom={9} />);
    const map = instances[0]!;
    expect(map.options.style).toBe('https://example.org/style.json');
    expect(map.options.center).toEqual([15, 45]);
    expect(map.options.zoom).toBe(9);
  });

  it('exposes the map instance via onLoad, once', () => {
    const onLoad = vi.fn();
    render(<MapView onLoad={onLoad} />);
    const map = instances[0]!;
    expect(onLoad).not.toHaveBeenCalled();
    act(() => map.emit('load'));
    act(() => map.emit('load'));
    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(onLoad).toHaveBeenCalledWith(map);
  });

  it('falls back to OSM raster tiles when the vector style fails, and tells the user', () => {
    const onLoad = vi.fn();
    render(<MapView onLoad={onLoad} fallbackRasterUrl="https://tiles.example/{z}/{x}/{y}.png" />);
    const map = instances[0]!;
    act(() => map.emit('error', { error: new Error('style 503') }));
    expect(map.styles).toHaveLength(1);
    expect(map.styles[0]).toEqual(rasterFallbackStyle('https://tiles.example/{z}/{x}/{y}.png'));
    expect(screen.getByText(/pričuvna OpenStreetMap karta/)).toBeTruthy();
    // the fallback style is "ready" on its first idle
    expect(onLoad).not.toHaveBeenCalled();
    act(() => map.emit('idle'));
    expect(onLoad).toHaveBeenCalledWith(map);
    // a second error does not switch styles again
    act(() => map.emit('error', { error: new Error('again') }));
    expect(map.styles).toHaveLength(1);
  });

  it('default fallback is the OSM raster tile server and keeps the attribution', () => {
    render(<MapView />);
    const map = instances[0]!;
    act(() => map.emit('error', { error: new Error('x') }));
    const style = map.styles[0] as ReturnType<typeof rasterFallbackStyle>;
    const source = style.sources['osm-raster'] as { tiles: string[]; attribution: string };
    expect(source.tiles).toEqual(['https://tile.openstreetmap.org/{z}/{x}/{y}.png']);
    expect(source.attribution).toBe('© OpenStreetMap contributors');
  });

  it('does not fall back for tile/source errors or after the map has loaded', () => {
    render(<MapView />);
    const map = instances[0]!;
    act(() => map.emit('error', { sourceId: 'openmaptiles', error: new Error('tile 404') }));
    expect(map.styles).toHaveLength(0);
    act(() => map.emit('load'));
    act(() => map.emit('error', { error: new Error('late') }));
    expect(map.styles).toHaveLength(0);
  });

  it('removes the map on unmount', () => {
    const { unmount } = render(<MapView />);
    const map = instances[0]!;
    expect(map.removed).toBe(false);
    unmount();
    expect(map.removed).toBe(true);
  });

  it('disables tile fade animation when the user prefers reduced motion', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce') }));
    render(<MapView />);
    expect(instances[0]!.options.fadeDuration).toBe(0);
    cleanup();
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    render(<MapView />);
    expect(instances[1]!.options.fadeDuration).toBe(300);
  });
});
