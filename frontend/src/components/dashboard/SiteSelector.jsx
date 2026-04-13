/**
 * Compact site selector for the Dashboard overview header.
 * Only renders when there are 2 or more sites.
 *
 * Props:
 *   sites      — array of { site_id, name }
 *   selectedId — site_id of the currently selected site
 *   onChange   — callback(site_id: string)
 */
export default function SiteSelector({ sites, selectedId, onChange }) {
  if (!sites || sites.length < 2) return null;

  return (
    <select
      value={selectedId || ''}
      onChange={e => onChange(e.target.value)}
      className="text-[9px] font-mono text-gray-600 bg-gray-50 border border-gray-200 rounded px-1.5 py-0.5 focus:outline-none focus:border-indigo-400 cursor-pointer shadow-sm"
    >
      {sites.map(s => (
        <option key={s.site_id} value={s.site_id}>
          {s.name}
        </option>
      ))}
    </select>
  );
}
