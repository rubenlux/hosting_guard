import { motion } from 'framer-motion';

/**
 * Single-row realtime status bar for the Dashboard overview.
 *
 * Props:
 *   active    — number of currently active users
 *   lastPath  — path string of the most recent page view (or null)
 *   lastTime  — human-readable time since last event, e.g. "12s" (or null)
 *   isLive    — boolean; controls pulse animation on the indicator dot
 */
export default function RealtimeMini({ active, lastPath, lastTime, isLive }) {
  return (
    <div className="text-[10px] font-mono text-gray-500 border-t border-white/5 pt-2">

      <div className="flex items-center gap-2">
        {isLive ? (
          <motion.div
            className="w-2 h-2 bg-emerald-400 rounded-full shrink-0"
            animate={{ scale: [1, 1.6, 1] }}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
          />
        ) : (
          <div className="w-2 h-2 rounded-full bg-white/10 shrink-0" />
        )}

        <span className="text-white">
          {active === 0
            ? 'Sin usuarios activos'
            : `${active} ${active === 1 ? 'usuario activo' : 'usuarios activos'} ahora`}
        </span>

        {isLive && (
          <span className="text-[9px] font-mono text-emerald-400 opacity-60">live</span>
        )}
      </div>

      {lastPath && (
        <div className="mt-1 ml-4 flex items-center gap-1.5">
          <span className="text-gray-600">Última visita:</span>
          <span className="truncate max-w-[160px] text-gray-400">{lastPath}</span>
          {lastTime && <span className="text-gray-600">· {lastTime}</span>}
        </div>
      )}

    </div>
  );
}
