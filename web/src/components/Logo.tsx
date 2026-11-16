/**
 * Cuepoint logo: concentric rings of evenly spaced dots around a red label.
 * Each ring uses pathLength = its dot count, so dots are spaced exactly
 * evenly with no seam where the ring closes.
 */

const FULL_RINGS: [r: number, dots: number][] = [
  [100, 55], [113, 62], [126, 69], [139, 76], [152, 83],
  [165, 90], [178, 97], [191, 104], [204, 111], [217, 119],
  [230, 126], [243, 133], [256, 140], [269, 147], [282, 154],
];

const MINI_RINGS: [r: number, dots: number][] = [
  [30, 25], [39, 33], [47, 39],
];

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 600 600" role="img" aria-label="Cuepoint logo">
      <g fill="none" stroke="var(--ink)" strokeWidth={5} strokeLinecap="round" strokeDasharray="0 1">
        {FULL_RINGS.map(([r, dots]) => (
          <circle key={r} cx={300} cy={300} r={r} pathLength={dots} />
        ))}
      </g>
      <circle cx={300} cy={300} r={80} fill="var(--accent)" />
      <circle cx={300} cy={300} r={9} fill="var(--paper)" />
    </svg>
  );
}

export function LogoMini({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <g fill="none" stroke="var(--ink)" strokeWidth={4} strokeLinecap="round" strokeDasharray="0 1">
        {MINI_RINGS.map(([r, dots]) => (
          <circle key={r} cx={50} cy={50} r={r} pathLength={dots} />
        ))}
      </g>
      <circle cx={50} cy={50} r={20} fill="var(--accent)" />
      <circle cx={50} cy={50} r={3.5} fill="var(--paper)" />
    </svg>
  );
}

/** "cuepoint" with the accent dot over the i. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={`wordmark ${className ?? ''}`} aria-hidden="true">
      cuepo<span className="wordmark-i">ı</span>nt
    </span>
  );
}
