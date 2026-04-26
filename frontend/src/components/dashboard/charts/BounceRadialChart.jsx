export default function BounceRadialChart({ bounceRate }) {
  const rate = Math.min(Math.max(bounceRate || 0, 0), 100);
  const retention = 100 - rate;
  const noData = rate >= 100;

  const color = noData ? '#555' : retention >= 60 ? '#3b82f6' : retention >= 40 ? '#f59e0b' : '#ef4444';
  const label = noData ? 'Sin datos' : retention >= 60 ? 'Buena' : retention >= 40 ? 'Regular' : 'Baja';

  return (
    <div style={{ background: '#121214', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minHeight: 160 }}>
      <div>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#888', marginBottom: 4 }}>Retención</div>
        <div style={{ fontSize: 11, color: '#444' }}>Usuarios que continúan navegando</div>
      </div>

      <div style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 12 }}>
          <span style={{ fontSize: 36, fontWeight: 900, color: noData ? '#333' : '#fff', lineHeight: 1 }}>
            {noData ? '—' : `${retention.toFixed(0)}%`}
          </span>
          {!noData && <span style={{ fontSize: 11, color: '#555' }}>retención</span>}
        </div>

        <div style={{ width: '100%', height: 4, background: 'rgba(255,255,255,0.05)', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${noData ? 0 : retention}%`, background: color, borderRadius: 4, transition: 'width 0.8s ease' }} />
        </div>

        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
          <span style={{ fontSize: 10, color, fontWeight: 700 }}>{label}</span>
          {!noData && <span style={{ fontSize: 10, color: '#444' }}>· Rebote: {rate.toFixed(0)}%</span>}
        </div>
      </div>
    </div>
  );
}
