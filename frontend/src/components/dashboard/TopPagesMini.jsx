import { motion } from 'framer-motion';

/**
 * Minimal table of top pages — staggered fade-in on mount.
 *
 * Props:
 *   pages — array of { path, views, url } (max 3 expected)
 */
export default function TopPagesMini({ pages }) {
  if (!pages || pages.length === 0) return null;

  return (
    <div className="space-y-2">
      {pages.map((page, i) => (
        <motion.div
          key={page.url || i}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.04, duration: 0.2 }}
          className="flex items-center justify-between gap-3"
        >
          <span className="text-[10px] font-mono text-gray-600 w-3 shrink-0">{i + 1}</span>
          <span
            className="flex-1 truncate text-[11px] font-mono text-gray-300"
            title={page.url}
          >
            {page.path}
          </span>
          <span className="text-[11px] font-mono text-gray-900 font-semibold shrink-0">
            {page.views}
          </span>
        </motion.div>
      ))}
    </div>
  );
}
