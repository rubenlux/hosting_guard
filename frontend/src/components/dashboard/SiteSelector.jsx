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
      style={{ fontSize: 11, color: '#888', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, padding: '4px 8px', outline: 'none', cursor: 'pointer' }}
    >
      {sites.map(s => (
        <option key={s.site_id} value={s.site_id}>
          {s.name}
        </option>
      ))}
    </select>
  );
}
