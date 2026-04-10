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
    <div className="text-[10px] font-mono text-gray-400 space-y-0.5 mb-3">
      {pages.map((page, i) => (
        <div key={page.url || i} className="flex justify-between gap-2">
          <span className="text-gray-500">{i + 1}.</span>
          <span className="flex-1 truncate text-gray-300" title={page.url}>
            {page.path}
          </span>
          <span className="text-white font-bold">{page.views}</span>
        </div>
      ))}
    </div>
  );
}
