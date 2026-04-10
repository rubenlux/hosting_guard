/**
 * Hero section — first thing the user sees.
 * Shows global system status: active users + last event.
 *
 * Props:
 *   realtime — { active, lastPath, lastTime, isLive }
 */
export default function HeroSection({ realtime }) {
  const { active, lastPath, lastTime, isLive } = realtime;
  const isActive = active > 0;

  return (
    <div className="flex items-center justify-between py-3 mb-4 border-b border-white/5">

      {/* Status badge */}
      <div className="flex items-center gap-2">
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${
            isActive ? 'bg-[#00ff88] animate-pulse' : 'bg-white/20'
          }`}
        />
        <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-gray-400">
          {isActive ? 'Sistema activo' : 'Sin actividad'}
        </span>
      </div>

      {/* Active users — big */}
      <div className="text-right">
        <div className={`text-2xl font-black font-mono leading-none ${isActive ? 'text-[#00ff88]' : 'text-gray-600'}`}>
          {active}
        </div>
        <div className="text-[9px] font-mono text-gray-500 mt-0.5">
          {active === 1 ? 'usuario activo' : 'usuarios activos'}
        </div>
      </div>

      {/* Last event */}
      {lastPath && (
        <div className="text-right max-w-[140px]">
          <div className="text-[9px] font-mono text-gray-500 uppercase tracking-widest mb-0.5">
            Última actividad
          </div>
          <div className="text-[10px] font-mono text-gray-300 truncate" title={lastPath}>
            {lastPath}
          </div>
          {lastTime && (
            <div className="text-[9px] font-mono text-gray-600">{lastTime} ago</div>
          )}
        </div>
      )}

    </div>
  );
}
