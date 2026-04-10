/**
 * IA Advisory insight card — subtle amber, no heavy gradient.
 *
 * Props:
 *   insight — { message: string } | null
 */
export default function InsightCard({ insight }) {
  if (!insight) return null;

  return (
    <div className="bg-amber-500/5 border border-amber-400/20 rounded-lg p-4">

      <div className="flex justify-between items-start gap-3">

        <div>
          <p className="text-[10px] font-mono text-amber-300 uppercase tracking-wide mb-1">
            IA Advisory
          </p>
          <p className="text-sm text-white">
            {insight.message}
          </p>
        </div>

        <button className="text-xs bg-emerald-500 text-black px-3 py-1 rounded shrink-0">
          Diagnosticar
        </button>

      </div>

    </div>
  );
}
