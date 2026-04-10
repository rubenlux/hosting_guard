/**
 * IA Insight card — gives chips protagonist role.
 * Renders nothing when chips array is empty.
 *
 * Props:
 *   chips — string[] (max 4, computed on server)
 */
export default function IAInsightCard({ chips }) {
  if (!chips || chips.length === 0) return null;

  return (
    <div className="bg-white/[0.03] border border-[#00ff88]/10 rounded-lg px-4 py-3 mb-4">

      <div className="flex items-center gap-2 mb-3">
        <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-[#00ff88]">
          🤖 Insight IA
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {chips.map((chip, i) => (
          <span
            key={i}
            className="bg-[#00ff88]/5 border border-[#00ff88]/15 px-2.5 py-1 rounded-md text-[10px] font-mono text-gray-200"
          >
            {chip}
          </span>
        ))}
      </div>

      <button className="text-[9px] font-mono text-[#00ff88] border border-[#00ff88]/20 px-3 py-1 rounded hover:bg-[#00ff88]/5 transition-colors">
        Diagnosticar →
      </button>

    </div>
  );
}
