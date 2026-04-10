/**
 * Minimal table of top pages — no boxes, no noise.
 *
 * Props:
 *   pages — array of { path, views, url } (max 3 expected)
 */
export default function TopPagesMini({ pages }) {
  if (!pages || pages.length === 0) return null;

  return (
    <div className="space-y-2">
      {pages.map((page, i) => (
        <div key={page.url || i} className="flex items-center justify-between gap-3">
          <span className="text-[10px] font-mono text-gray-600 w-3 shrink-0">{i + 1}</span>
          <span
            className="flex-1 truncate text-[11px] font-mono text-gray-300"
            title={page.url}
          >
            {page.path}
          </span>
          <span className="text-[11px] font-mono text-white font-semibold shrink-0">
            {page.views}
          </span>
        </div>
      ))}
    </div>
  );
}
