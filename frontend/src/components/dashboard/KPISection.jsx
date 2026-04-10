/**
 * Horizontal KPI strip — no cards, Vercel-style minimal layout.
 *
 * Props:
 *   kpis — { visits, sessions, bounceRate, active }
 */
export default function KPISection({ kpis }) {
  if (!kpis) return null;

  return (
    <div className="grid grid-cols-4 gap-6 mb-6">

      <KPI label="Visitas"  value={kpis.visits} />
      <KPI label="Sesiones" value={kpis.sessions} />

      <KPI
        label="Bounce"
        value={`${kpis.bounceRate}%`}
        color={
          kpis.bounceRate > 50 ? 'text-red-400'
          : kpis.bounceRate > 30 ? 'text-yellow-400'
          : 'text-emerald-400'
        }
      />

      <KPI label="Activos" value={kpis.active} />

    </div>
  );
}

function KPI({ label, value, color = 'text-white' }) {
  return (
    <div>
      <p className="text-[10px] font-mono text-gray-500 uppercase tracking-wide">
        {label}
      </p>
      <p className={`text-xl font-semibold mt-1 ${color}`}>
        {value}
      </p>
    </div>
  );
}
