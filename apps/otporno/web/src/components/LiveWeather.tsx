import { formatDateTime } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { fmtDec } from '../lib/format';

interface Props {
  lat: number;
  lon: number;
}

/** Latest DHMZ observation of the nearest station. Hidden by the API when older than 3 hours. */
export function LiveWeather({ lat, lon }: Props) {
  const q = useQuery({
    queryKey: ['dhmz', lat, lon],
    queryFn: ({ signal }) => api.liveDhmz(lat, lon, signal),
    staleTime: 10 * 60_000,
    retry: false,
  });
  if (q.isPending) return null;
  const s = q.data?.stations[0];
  return (
    <section aria-labelledby="live-h" className="ot-card p-5">
      <h2 id="live-h" className="ot-display text-xl">
        Trenutno vrijeme u blizini
      </h2>
      {q.isError ? (
        <p className="mt-2 text-neutral-700">Podaci DHMZ-a trenutno nisu dostupni.</p>
      ) : q.data?.status === 'stale' ? (
        <p className="mt-2 text-neutral-700">{q.data.message}</p>
      ) : s ? (
        <>
          <p className="mt-2 text-lg">
            <strong>{s.name}</strong> ({fmtDec(s.distance_km)} km od adrese):{' '}
            <span className="ot-num font-bold">{fmtDec(s.temp_c)} °C</span>
            {s.condition ? `, ${s.condition}` : ''}
            {s.humidity_pct != null ? `, vlaga ${Math.round(s.humidity_pct)} %` : ''}
            {s.wind_ms != null ? `, vjetar ${s.wind_dir ?? ''} ${fmtDec(s.wind_ms)} m/s` : ''}.
          </p>
          <p className="mt-1 text-sm text-neutral-700">
            Mjereno {formatDateTime(q.data!.observed_at)}. {q.data!.attribution}.
          </p>
        </>
      ) : (
        <p className="mt-2 text-neutral-700">Nema DHMZ postaje u krugu od 60 km.</p>
      )}
    </section>
  );
}
