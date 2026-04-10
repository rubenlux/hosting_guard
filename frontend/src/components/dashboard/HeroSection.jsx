/**
 * Hero section — global system status at a glance.
 *
 * Props:
 *   realtime — { active, lastPath, lastTime, isLive }
 *   kpis     — { visits, sessions, bounceRate, active }
 */
export default function HeroSection({ realtime, kpis }) {
  const isLive = realtime?.active > 0;

  return (
    <div className="bg-gradient-to-r from-emerald-500/10 to-cyan-500/10 border border-white/10 rounded-xl p-4 mb-4">

      <div className="flex items-center justify-between">

        <div>
          <p className="text-[11px] font-mono text-gray-400">
            Estado del sistema
          </p>

          <h2 className="text-lg font-semibold text-white mt-1">
            {isLive ? '🟢 Usuarios activos ahora' : '⚪ Sin actividad en tiempo real'}
          </h2>

          <p className="text-xs text-gray-400 mt-1">
            {realtime?.lastPath
              ? `${realtime.lastPath} · hace ${realtime.lastTime}`
              : 'Sin tráfico reciente'}
          </p>
        </div>

        <div className="text-right">
          <p className="text-2xl font-bold text-emerald-400">
            {realtime?.active ?? 0}
          </p>
          <p className="text-[10px] text-gray-500 font-mono">
            activos
          </p>
        </div>

      </div>
    </div>
  );
}
