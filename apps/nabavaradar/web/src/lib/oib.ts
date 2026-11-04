/** OIB checksum (ISO 7064, MOD 11,10) - the same algorithm as the API. */
export function isValidOib(value: string): boolean {
  if (!/^\d{11}$/.test(value)) return false;
  let a = 10;
  for (let i = 0; i < 10; i += 1) {
    a = (a + Number(value[i])) % 10;
    if (a === 0) a = 10;
    a = (a * 2) % 11;
  }
  let check = 11 - a;
  if (check === 10) check = 0;
  return check === Number(value[10]);
}

export type OibStatus = 'empty' | 'incomplete' | 'invalid' | 'valid';

/** Inline validation state for the input and a Croatian message for it. */
export function oibStatus(raw: string): { status: OibStatus; message: string } {
  const value = raw.trim();
  if (value === '') return { status: 'empty', message: '' };
  if (/\D/.test(value)) return { status: 'invalid', message: 'OIB smije sadržavati samo znamenke.' };
  if (value.length < 11)
    return { status: 'incomplete', message: `Još ${11 - value.length} znamenki do 11.` };
  if (value.length > 11) return { status: 'invalid', message: 'OIB ima točno 11 znamenki.' };
  return isValidOib(value)
    ? { status: 'valid', message: 'OIB je ispravan.' }
    : { status: 'invalid', message: 'Kontrolna znamenka ne odgovara: provjerite OIB.' };
}
