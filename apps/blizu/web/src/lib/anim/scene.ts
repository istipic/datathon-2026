/** Scene state machine: idle -> doseg <-> put <-> 3d, mirrored in the URL as ?scena=doseg|put|3d. */
export type Scene = 'idle' | 'doseg' | 'put' | '3d';
export type ActiveScene = Exclude<Scene, 'idle'>;
export const SCENES: ActiveScene[] = ['doseg', 'put', '3d'];

export const SCENE_LABEL: Record<ActiveScene, string> = {
  doseg: 'Doseg pješice',
  put: 'Put do…',
  '3d': '3D',
};

export function parseScene(search: string | URLSearchParams): Scene {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search;
  const value = params.get('scena');
  return value === 'doseg' || value === 'put' || value === '3d' ? value : 'idle';
}

/** Returns a copy of the params with the scene set (idle removes the parameter). */
export function withScene(params: URLSearchParams, scene: Scene): URLSearchParams {
  const copy = new URLSearchParams(params);
  if (scene === 'idle') copy.delete('scena');
  else copy.set('scena', scene);
  return copy;
}

/**
 * The scene a request leads to. "idle" is only the start state and can never be requested back;
 * every active scene can be entered from any other (the switcher is a segmented control).
 */
export function nextScene(current: Scene, requested: Scene): Scene {
  return requested === 'idle' ? current : requested;
}

/** Scene a freshly loaded results page starts in: the URL wins, otherwise the flood. */
export function initialScene(search: string | URLSearchParams): ActiveScene {
  const parsed = parseScene(search);
  return parsed === 'idle' ? 'doseg' : parsed;
}

/** Whether the 3D scene may be used (vector style loaded, i.e. not the raster fallback). */
export function threeDAvailable(usingFallback: boolean): boolean {
  return !usingFallback;
}
