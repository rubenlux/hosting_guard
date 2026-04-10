/**
 * Single-row realtime status bar for the Dashboard overview.
 * Shows active user count and the most recently visited path.
 *
 * Props:
 *   active    — number of currently active users
 *   lastPath  — path string of the most recent page view (or null)
 *   lastTime  — human-readable time since last event, e.g. "12s" (or null)
 *   isLive    — boolean; controls pulse animation on the indicator dot
 */
export default function RealtimeMini({ active, lastPath, lastTime, isLive }) {
  return (
    <div className="text-[10px] font-mono text-gray-500 border-t border-white/5 pt-2 flex items-center gap-2">
      <span
        className={`w-1.5 h-1.5 rounded-full bg-accent shrink-0 ${isLive ? 'animate-pulse' : 'opacity-30'}`}
      />
      <span className="text-white">{active} activos</span>

      {lastPath && (
        <>
          <span>│</span>
          <span className="truncate max-w-[160px]">{lastPath}</span>
          {lastTime && <span>{lastTime}</span>}
        </>
      )}
    </div>
  );
}
