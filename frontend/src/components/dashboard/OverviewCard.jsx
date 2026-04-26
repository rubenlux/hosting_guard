import { useNavigate } from 'react-router-dom';
import { BarChart3, ExternalLink } from 'lucide-react';

export default function OverviewCard({ siteName, headerExtra, children }) {
  const navigate = useNavigate();

  return (
    <div style={{ background: '#121214', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, padding: '20px', marginBottom: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(59,130,246,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <BarChart3 size={16} color="#3b82f6" />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>Analytics</div>
            <div style={{ fontSize: 11, color: '#555' }}>{siteName || 'Tu sitio'}</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {headerExtra}
          <button
            onClick={() => navigate('/pixel')}
            style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '5px 10px', color: '#888', fontSize: 11, cursor: 'pointer', transition: 'all 0.15s' }}
            onMouseEnter={e => { e.currentTarget.style.color = '#fff'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.15)'; }}
            onMouseLeave={e => { e.currentTarget.style.color = '#888'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'; }}
          >
            <ExternalLink size={11} /> Ver todo
          </button>
        </div>
      </div>
      {children}
    </div>
  );
}
