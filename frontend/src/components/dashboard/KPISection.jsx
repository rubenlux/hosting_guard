/**
 * Four-column KPI grid for the analytics overview.
 *
 * Props:
 *   kpis — { visits, sessions, bounceRate, active }
 */
export default function KPISection({ kpis }) {
  const items = [
    { value: kpis.visits,     label: 'visitas',  color: 'text-[#00ff88]' },
    { value: kpis.sessions,   label: 'sesiones', color: 'text-[#00aaff]' },
    { value: `${kpis.bounceRate}%`, label: 'bounce', color: 'text-[#ffaa00]' },
    { value: kpis.active,     label: 'activos',  color: 'text-[#00ff88]' },
  ];

  return (
    <div className="grid grid-cols-4 text-center mb-3">
      {items.map(({ value, label, color }) => (
        <div key={label}>
          <div className={`text-xl font-black font-mono ${color}`}>{value}</div>
          <div className="text-[9px] text-gray-500 font-mono">{label}</div>
        </div>
      ))}
    </div>
  );
}
