import { Radio } from 'lucide-react';

export default function ActiveUsersPulse({ active = 0 }) {
  const isLive = active > 0;

  return (
    <div style={{ background: '#121214', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minHeight: 160 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Radio size={13} color={isLive ? '#00ff88' : '#444'} />
        <span style={{ fontSize: 11, fontWeight: 700, color: isLive ? '#00ff88' : '#555' }}>En vivo</span>
        {isLive && <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#00ff88', animation: 'pulse 1.5s infinite', marginLeft: 2 }} />}
      </div>

      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: 36, fontWeight: 900, color: isLive ? '#fff' : '#333', lineHeight: 1, marginBottom: 6 }}>
          {active}
        </div>
        <div style={{ fontSize: 11, color: '#555' }}>
          {isLive ? `usuario${active !== 1 ? 's' : ''} activo${active !== 1 ? 's' : ''}` : 'sin actividad ahora'}
        </div>
      </div>
    </div>
  );
}
