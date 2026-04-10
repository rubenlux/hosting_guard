/**
 * IA Advisory insight card — protagonist placement, above KPIs.
 *
 * Props:
 *   insight — { message: string } | null
 */
export default function InsightCard({ insight }) {
  if (!insight) return null;

  return (
    <div className="bg-gradient-to-r from-amber-500/10 to-orange-500/10 border border-amber-400/20 rounded-xl p-4 mb-4">

      <div className="flex justify-between items-start">

        <div>
          <p className="text-[10px] font-mono text-amber-300">
            IA ADVISORY
          </p>

          <p className="text-sm text-white mt-1">
            {insight.message}
          </p>
        </div>

        <button className="text-xs bg-emerald-500 text-black px-3 py-1 rounded shrink-0 ml-3">
          Diagnosticar
        </button>

      </div>
    </div>
  );
}
