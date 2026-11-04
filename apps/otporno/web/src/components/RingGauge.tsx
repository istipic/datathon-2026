import { BANDS, BAND_LABEL, HEAT_FILL, bandIndex } from '../lib/bands';
import type { Band } from '../lib/types';

interface Props {
  band: Band | null;
  /** Text in the middle when the band is unknown. */
  unknownLabel?: string;
  hazard: string;
}

const R = 46;
const C = 2 * Math.PI * R;
const GAP = 6; // px of circumference between segments

/**
 * Four-segment ring (one segment per band, filled up to the current band) with the band spelled
 * out in the centre: the colour is never the only signal.
 */
export function RingGauge({ band, unknownLabel = 'Nije određeno', hazard }: Props) {
  const idx = bandIndex(band);
  const seg = C / 4;
  const label = band
    ? `${hazard}: razina ${BAND_LABEL[band].toLowerCase()}`
    : `${hazard}: ${unknownLabel.toLowerCase()}`;
  return (
    <figure className="m-0 grid place-items-center" aria-label={label}>
      <svg viewBox="0 0 120 120" width="132" height="132" role="img" aria-label={label}>
        {BANDS.map((b, i) => (
          <circle
            key={b}
            cx="60"
            cy="60"
            r={R}
            fill="none"
            strokeWidth="12"
            stroke={i <= idx ? HEAT_FILL[BANDS[Math.max(idx, 0)] as Band] : '#E8E2D6'}
            strokeDasharray={`${seg - GAP} ${C - seg + GAP}`}
            strokeDashoffset={-i * seg + (i === 0 ? 0 : 0)}
            transform="rotate(-135 60 60)"
            strokeLinecap="butt"
          />
        ))}
        <text x="60" y="64" textAnchor="middle" fontSize="26" fontWeight="700" fill="#1C1917">
          {band ? `${idx + 1}/4` : '?'}
        </text>
        <text x="60" y="80" textAnchor="middle" fontSize="11" fill="#57534E">
          razina
        </text>
      </svg>
      <figcaption className="mt-1 text-center text-base font-bold">
        {band ? BAND_LABEL[band] : unknownLabel}
      </figcaption>
    </figure>
  );
}
