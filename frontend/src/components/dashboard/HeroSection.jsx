/**
 * Hero section — full-width, no card, Stripe-style air + typography.
 *
 * Props:
 *   realtime — { active, lastPath, lastTime, isLive }
 */
export default function HeroSection({ realtime }) {
  const active = realtime?.active ?? 0;

  return (
    <div className="mb-6">

      <div className="flex items-end justify-between">

        <div>
          <p className="text-[10px] font-mono text-gray-500 uppercase tracking-wide">
            Estado en tiempo real
          </p>

          <h1 className="text-2xl font-semibold text-gray-900 mt-1">
            {active > 0 ? 'Usuarios activos ahora' : 'Sin actividad en tiempo real'}
          </h1>

          <p className="text-sm text-gray-400 mt-1">
            {realtime?.lastPath
              ? `${realtime.lastPath} · hace ${realtime.lastTime}`
              : 'Sin tráfico reciente'}
          </p>
        </div>

        <div className="text-right">
          <p className="text-4xl font-bold text-gray-900">
            {active}
          </p>
          <p className="text-xs text-gray-500 font-mono">
            activos
          </p>
        </div>

      </div>

      <div className="mt-4 h-px bg-white/5" />

    </div>
  );
}
