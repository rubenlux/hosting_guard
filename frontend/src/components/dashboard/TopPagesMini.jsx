/**
 * Text-only list of top pages for the Dashboard overview.
 * No charts, no bars — just rank, path, and view count.
 *
 * Props:
 *   pages — array of { path, views, url } (max 3 expected)
 */
export default function TopPagesMini({ pages }) {
  if (!pages || pages.length === 0) return null;

  return (
    <div className="text-[10px] font-mono text-gray-400 space-y-1">
      {pages.map((page, i) => {
        const isTop = i === 0;
        return (
          <div
            key={page.url || i}
            className={`flex items-center justify-between gap-2 ${
              isTop ? 'bg-white/[0.03] rounded px-2 py-1' : 'px-2'
            }`}
          >
            <span className="text-gray-600 shrink-0">
              {isTop ? '🔥' : `${i + 1}.`}
            </span>
            <span className="flex-1 truncate text-gray-300" title={page.url}>
              {page.path}
            </span>
            {isTop && (
              <span className="text-[8px] font-mono text-[#00ff88] shrink-0 mr-1">
                más visitada
              </span>
            )}
            <span className="text-white font-bold shrink-0">{page.views}</span>
          </div>
        );
      })}
    </div>
  );
}
