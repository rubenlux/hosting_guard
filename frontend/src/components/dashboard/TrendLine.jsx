import React from 'react';

/**
 * Renders a small sparkline SVG from an array of health-check objects.
 * Shows a "CALIBRANDO..." placeholder when there are fewer than 2 data points.
 *
 * Props:
 *   data  — array of { score: number } objects
 *   color — stroke color (default: #00ff88)
 */
export default function TrendLine({ data, color = '#00ff88' }) {
  if (!data || data.length < 2) {
    return (
      <div className="h-[25px] flex items-center text-[9px] text-gray-700 font-mono italic">
        CALIBRANDO...
      </div>
    );
  }

  const scores  = data.map(d => d.score);
  const padding = 2;
  const width   = 80;
  const height  = 25;

  const points = scores
    .map((s, i) => {
      const x = (i / (scores.length - 1)) * width;
      const y = height - (s / 100) * (height - padding * 2) - padding;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        style={{ filter: `drop-shadow(0 0 5px ${color}40)` }}
      />
    </svg>
  );
}
