/** Example addresses for the home page. Each one is verified through /api/v1/geocode before use. */
export interface ExampleAddress {
  label: string;
  query: string;
  lat: number;
  lon: number;
}
export const EXAMPLES: ExampleAddress[] = [];
