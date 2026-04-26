import { Database, Clock, Download, RotateCcw, Shield } from 'lucide-react';

const features = [
  { icon: Clock, label: 'Backups automáticos diarios', desc: 'Tu sitio se respalda automáticamente cada noche.' },
  { icon: Download, label: 'Descarga directa', desc: 'Descargá cualquier backup en formato .zip desde el panel.' },
  { icon: RotateCcw, label: 'Restauración con 1 clic', desc: 'Revertí tu sitio a cualquier punto en el tiempo.' },
  { icon: Shield, label: 'Retención de 30 días', desc: 'Mantenemos 30 días de historial de backups.' },
];

const BackupsSection = () => (
  <div style={{ maxWidth: 700, margin: '0 auto' }}>
    <div style={{ marginBottom: 32 }}>
      <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', marginBottom: 6 }}>Backups</div>
      <div style={{ fontSize: 13, color: '#666' }}>Respaldos automáticos y restauración de tu sitio.</div>
    </div>

    {/* Coming soon hero */}
    <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 20, padding: '48px 32px', textAlign: 'center', marginBottom: 24 }}>
      <div style={{ width: 72, height: 72, borderRadius: 20, background: 'rgba(129,140,248,0.1)', border: '1px solid rgba(129,140,248,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
        <Database size={32} color="#818cf8" />
      </div>
      <div style={{ fontSize: 20, fontWeight: 800, color: '#fff', marginBottom: 8 }}>Próximamente</div>
      <div style={{ fontSize: 13, color: '#666', maxWidth: 400, margin: '0 auto', lineHeight: 1.6 }}>
        El sistema de backups está en desarrollo. Pronto podrás crear, descargar y restaurar respaldos directamente desde aquí.
      </div>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 20, background: 'rgba(129,140,248,0.08)', border: '1px solid rgba(129,140,248,0.2)', borderRadius: 20, padding: '6px 16px' }}>
        <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#818cf8', animation: 'pulse 2s infinite' }} />
        <span style={{ fontSize: 11, color: '#818cf8', fontWeight: 700 }}>EN DESARROLLO</span>
      </div>
    </div>

    {/* Feature preview */}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      {features.map(({ icon: Icon, label, desc }) => (
        <div key={label} style={{ background: '#111', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 12, padding: '16px 18px', opacity: 0.6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <Icon size={16} color="#818cf8" />
            <span style={{ fontSize: 12, fontWeight: 700, color: '#fff' }}>{label}</span>
          </div>
          <div style={{ fontSize: 11, color: '#666', lineHeight: 1.5 }}>{desc}</div>
        </div>
      ))}
    </div>
  </div>
);

export default BackupsSection;
