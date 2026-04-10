/**
 * Minimal SVG sparkline — polyline only, no fill, no animation.
 * Designed for the Dashboard overview (max 120px height).
 *
 * Props:
 *   data — array of objects with a `page_views` numeric field
 */
export default function SparklineChart({ data }) {
  if (!data || data.length < 2) {
    return <div className="h-[48px] border-b border-white/5" />;
  }

  const vals = data.map(d => d.page_views || 0);
  const maxY  = Math.max(...vals, 1);
  const n     = vals.length;
  const W = 300, H = 48, px = 2, py = 4;

  const points = vals
    .map((v, i) => {
      const x = px + (i / (n - 1)) * (W - px * 2);
      const y = H - py - (v / maxY) * (H - py * 2);
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      style={{ height: 48 }}
      preserveAspectRatio="none"
    >
      <polyline
        fill="none"
        stroke="#00ff88"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        opacity="0.65"
      />
    </svg>
  );
}
