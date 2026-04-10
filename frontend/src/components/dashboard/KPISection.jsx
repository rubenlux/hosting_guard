/**
 * Four-column KPI grid for the analytics overview.
 *
 * Props:
 *   kpis — { visits, sessions, bounceRate, active }
 */
export default function KPISection({ kpis }) {
  const bounceColor = kpis.bounceRate > 50 ? 'text-red-400'
    : kpis.bounceRate > 30 ? 'text-yellow-400'
    : 'text-emerald-400';

  const bounceLabel = kpis.bounceRate > 40 ? 'bounce alto' : 'bounce normal';

  const items = [
    { value: kpis.visits,              label: 'visitas',     color: 'text-[#00ff88]' },
    { value: kpis.sessions,            label: 'sesiones',    color: 'text-[#00aaff]' },
    { value: `${kpis.bounceRate}%`,    label: bounceLabel,   color: bounceColor       },
    { value: kpis.active,              label: 'activos',     color: 'text-[#00ff88]' },
  ];

  return (
    <div className="grid grid-cols-4 text-center">
      {items.map(({ value, label, color }) => (
        <div key={label}>
          <div className={`text-base font-black font-mono ${color}`}>{value}</div>
          <div className="text-[9px] text-gray-600 font-mono uppercase tracking-wider mt-0.5">{label}</div>
        </div>
      ))}
    </div>
  );
}
