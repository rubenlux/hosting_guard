import { useNavigate } from 'react-router-dom';
import { BarChart3, ArrowRight } from 'lucide-react';

export default function EmptyState({ hasSite = false }) {
  const navigate = useNavigate();

  return (
    <div style={{ background: '#121214', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, padding: '20px', marginBottom: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(59,130,246,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <BarChart3 size={16} color="#3b82f6" />
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>Analytics</div>
          <div style={{ fontSize: 11, color: '#555' }}>Métricas de tu sitio</div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px 16px', textAlign: 'center' }}>
        <div style={{ width: 48, height: 48, borderRadius: 12, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 14 }}>
          <BarChart3 size={22} color="#333" />
        </div>
        <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', marginBottom: 4 }}>
          {hasSite ? 'Sin tráfico aún' : 'Sin sitios registrados'}
        </div>
        <div style={{ fontSize: 11, color: '#555', maxWidth: 260, lineHeight: 1.6, marginBottom: 16 }}>
          {hasSite
            ? 'Una vez que tu sitio tenga visitas, las métricas aparecerán aquí.'
            : 'Registrá tu primer sitio para activar el seguimiento de tráfico.'}
        </div>
        <button
          onClick={() => navigate('/pixel')}
          style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.2)', borderRadius: 8, padding: '7px 14px', color: '#3b82f6', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
        >
          Ver instalación <ArrowRight size={13} />
        </button>
      </div>
    </div>
  );
}
