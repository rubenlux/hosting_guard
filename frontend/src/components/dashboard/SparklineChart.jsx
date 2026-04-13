import { motion } from 'framer-motion';

/**
 * Minimal SVG sparkline — animated path draw on mount.
 *
 * Props:
 *   data — array of objects with a `page_views` numeric field
 */
export default function SparklineChart({ data }) {
  if (!data || data.length < 2) {
    return <div className="h-[48px] bg-gray-50 border border-gray-100 rounded-lg animate-pulse" />;
  }

  const vals = data.map(d => d.page_views || 0);
  const maxY  = Math.max(...vals, 1);
  const n     = vals.length;
  const W = 300, H = 48, px = 2, py = 4;

  const d = vals
    .map((v, i) => {
      const x = px + (i / (n - 1)) * (W - px * 2);
      const y = H - py - (v / maxY) * (H - py * 2);
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    })
    .join(' ');

  return (
    <div className="bg-white border border-gray-100 rounded-lg p-4 shadow-sm">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ height: 48 }}
        preserveAspectRatio="none"
      >
        <motion.path
          d={d}
          fill="none"
          stroke="#00ff88"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.65"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
        />
      </svg>
    </div>
  );
}
