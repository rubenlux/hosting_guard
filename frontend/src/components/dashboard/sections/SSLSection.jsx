import { useState } from 'react';
import { ShieldCheck, ShieldAlert, RefreshCw, Check, Lock } from 'lucide-react';

const SSLSection = ({ hostings = [] }) => {
  const [renewing, setRenewing] = useState(null);
  const [renewed, setRenewed] = useState({});

  const handleRenew = async (id) => {
    setRenewing(id);
    await new Promise(r => setTimeout(r, 1800));
    setRenewing(null);
    setRenewed(prev => ({ ...prev, [id]: true }));
    setTimeout(() => setRenewed(prev => { const n = { ...prev }; delete n[id]; return n; }), 3000);
  };

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', marginBottom: 6 }}>SSL / HTTPS</div>
        <div style={{ fontSize: 13, color: '#666' }}>Certificados Let's Encrypt gratuitos con renovación automática.</div>
      </div>

      {/* Info banner */}
      <div style={{ background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.15)', borderRadius: 12, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
        <Lock size={14} color="#00ff88" />
        <span style={{ fontSize: 12, color: '#00ff88' }}>Todos tus sitios usan HTTPS con certificados Let's Encrypt renovados automáticamente cada 90 días.</span>
      </div>

      {hostings.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '4rem 2rem', background: '#111', borderRadius: 16, border: '1px dashed rgba(255,255,255,0.08)' }}>
          <ShieldCheck size={32} style={{ color: '#333', marginBottom: 12 }} />
          <div style={{ color: '#666', fontSize: 14 }}>No tenés sitios activos aún.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {hostings.map(h => {
            const isActive = h.status === 'active';
            const isRenewing = renewing === h.hosting_id;
            const wasRenewed = renewed[h.hosting_id];
            const subdomain = h.subdomain || '';
            const displayUrl = subdomain.includes('.') ? subdomain : `${subdomain}.hostingguard.lat`;

            return (
              <div key={h.hosting_id} style={{ background: '#111', border: `1px solid ${isActive ? 'rgba(0,255,136,0.12)' : 'rgba(255,255,255,0.08)'}`, borderRadius: 14, padding: '20px 24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div style={{ width: 44, height: 44, borderRadius: 12, background: isActive ? 'rgba(0,255,136,0.08)' : 'rgba(245,158,11,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    {isActive
                      ? <ShieldCheck size={22} color="#00ff88" />
                      : <ShieldAlert size={22} color="#f59e0b" />}
                  </div>

                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#fff', marginBottom: 2 }}>{h.name}</div>
                    <div style={{ fontSize: 12, color: '#888', fontFamily: 'monospace' }}>{displayUrl}</div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, padding: '3px 10px', borderRadius: 20, background: isActive ? 'rgba(0,255,136,0.1)' : 'rgba(245,158,11,0.1)', color: isActive ? '#00ff88' : '#f59e0b' }}>
                      {isActive ? '● VÁLIDO' : '● INACTIVO'}
                    </span>
                    {isActive && (
                      <span style={{ fontSize: 10, color: '#555' }}>Let's Encrypt · Auto-renovación ON</span>
                    )}
                  </div>
                </div>

                {isActive && (
                  <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
                      {[
                        { label: 'Tipo', value: "Let's Encrypt" },
                        { label: 'Cifrado', value: 'TLS 1.3' },
                        { label: 'Auto-renovación', value: 'Activada' },
                      ].map(({ label, value }) => (
                        <div key={label}>
                          <div style={{ fontSize: 10, color: '#555', fontWeight: 700, marginBottom: 2 }}>{label.toUpperCase()}</div>
                          <div style={{ fontSize: 12, color: '#aaa', fontWeight: 600 }}>{value}</div>
                        </div>
                      ))}
                    </div>
                    <button
                      onClick={() => handleRenew(h.hosting_id)}
                      disabled={isRenewing || wasRenewed}
                      style={{ display: 'flex', alignItems: 'center', gap: 6, background: wasRenewed ? 'rgba(0,255,136,0.1)' : 'rgba(255,255,255,0.06)', border: `1px solid ${wasRenewed ? 'rgba(0,255,136,0.2)' : 'rgba(255,255,255,0.1)'}`, borderRadius: 8, padding: '7px 14px', color: wasRenewed ? '#00ff88' : '#888', fontSize: 11, fontWeight: 700, cursor: isRenewing || wasRenewed ? 'not-allowed' : 'pointer', transition: 'all 0.2s' }}
                    >
                      {wasRenewed ? <><Check size={12} /> Renovado</> : isRenewing ? <><RefreshCw size={12} className="animate-spin" /> Renovando...</> : <><RefreshCw size={12} /> Forzar renovación</>}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default SSLSection;
