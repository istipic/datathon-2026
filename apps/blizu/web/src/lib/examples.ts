/**
 * Example addresses for the home page. Coordinates are the first result of
 * GET /api/v1/geocode?q=<query> (OpenStreetMap Nominatim) on 2026-11-03.
 */
export interface ExampleAddress {
  label: string;
  query: string;
  lat: number;
  lon: number;
}

export const EXAMPLES: ExampleAddress[] = [
  {
    label: 'Trg bana Jelačića 1',
    query: 'Trg bana Jelačića 1, Zagreb',
    lat: 45.81277,
    lon: 15.97659,
  },
  {
    label: 'Avenija Dubrovnik 15 (Novi Zagreb)',
    query: 'Avenija Dubrovnik 15, Zagreb',
    lat: 45.78044,
    lon: 15.97217,
  },
  {
    label: 'Trg Dragutina Domjanića 4 (Sesvete)',
    query: 'Trg Dragutina Domjanića 4, Sesvete',
    lat: 45.82657,
    lon: 16.11056,
  },
];
