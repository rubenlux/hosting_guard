/**
 * Skeleton placeholder matching the structure of BusinessOverview.
 * Shown while useDashboardData is loading — eliminates blank-screen flash.
 * No props, no logic.
 */

function Bone({ className }) {
  return (
    <div
      className={`bg-white/[0.06] rounded animate-pulse ${className}`}
    />
  );
}

export default function DashboardSkeleton() {
  return (
    <div className="bg-[#050505] border border-white/10 rounded-xl p-4 mb-6">

      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-white/10" />
          <Bone className="w-24 h-2.5" />
        </div>
        <Bone className="w-10 h-2" />
      </div>

      {/* KPIs — 4 columns */}
      <div className="grid grid-cols-4 text-center gap-2 mb-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="flex flex-col items-center gap-1.5">
            <Bone className="w-10 h-5" />
            <Bone className="w-8 h-1.5" />
          </div>
        ))}
      </div>

      {/* Chips */}
      <div className="flex gap-1.5 mb-3">
        {[...Array(3)].map((_, i) => (
          <Bone key={i} className="h-5 rounded" style={{ width: `${52 + i * 12}px` }} />
        ))}
      </div>

      {/* Sparkline */}
      <Bone className="w-full h-[48px] mb-3" />

      {/* Top pages */}
      <div className="space-y-1.5 mb-3">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="flex justify-between gap-2">
            <Bone className="w-4 h-2" />
            <Bone className="flex-1 h-2" />
            <Bone className="w-6 h-2" />
          </div>
        ))}
      </div>

      {/* Realtime row */}
      <div className="border-t border-white/5 pt-2 flex items-center gap-2">
        <div className="w-1.5 h-1.5 rounded-full bg-white/10" />
        <Bone className="w-16 h-2" />
        <Bone className="w-32 h-2" />
      </div>

    </div>
  );
}
