import { motion } from 'framer-motion';

/**
 * IA Advisory insight card — subtle amber, no heavy gradient.
 *
 * Props:
 *   insight — { message: string } | null
 */
export default function InsightCard({ insight }) {
  if (!insight) return null;

  return (
    <motion.div
      whileHover={{ scale: 1.01 }}
      transition={{ duration: 0.2 }}
      className="bg-amber-500/5 border border-amber-400/20 rounded-lg p-4"
    >

      <div className="flex justify-between items-start gap-3">

        <div>
          <p className="text-[10px] font-mono text-amber-300 uppercase tracking-wide mb-1">
            IA Advisory
          </p>
          <p className="text-sm text-white">
            {insight.message}
          </p>
        </div>

        <motion.button
          whileTap={{ scale: 0.96 }}
          whileHover={{ scale: 1.03 }}
          className="text-xs bg-emerald-500 text-black px-3 py-1 rounded shrink-0"
        >
          Diagnosticar
        </motion.button>

      </div>

    </motion.div>
  );
}
