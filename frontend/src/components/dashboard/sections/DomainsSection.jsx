import { useState } from 'react';
import { Globe, Copy, Check, ExternalLink, ChevronDown, ChevronUp, Info } from 'lucide-react';

const CopyBtn = ({ text }) => {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button onClick={handle} style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, padding: '3px 8px', cursor: 'pointer', color: copied ? '#00ff88' : '#888', display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, transition: 'all 0.15s' }}>
      {copied ? <Check size={11} /> : <Copy size={11} />}
      {copied ? 'Copiado' : 'Copiar'}
    </button>
  );
};

const STATUS_COLOR = { active: '#00ff88', stopped: '#f59e0b', error: '#ef4444', exited: '#f59e0b' };

const DomainsSection = ({ hostings = [] }) => {
  const [openCustom, setOpenCustom] = useState(null);
  const [customDomain, setCustomDomain] = useState('');

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', marginBottom: 6 }}>Dominios</div>
        <div style={{ fontSize: 13, color: '#666' }}>Administrá los dominios de tus sitios web.</div>
      </div>

      {hostings.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '4rem 2rem', background: '#111', borderRadius: 16, border: '1px dashed rgba(255,255,255,0.08)' }}>
          <Globe size={32} style={{ color: '#333', marginBottom: 12 }} />
          <div style={{ color: '#666', fontSize: 14 }}>No tenés sitios activos aún.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {hostings.map(h => {
            const subdomain = h.subdomain || '';
            const url = subdomain.includes('.') ? `https://${subdomain}` : `https://${subdomain}.hostingguard.lat`;
            const displayUrl = subdomain.includes('.') ? subdomain : `${subdomain}.hostingguard.lat`;
            const statusColor = STATUS_COLOR[h.status] || '#888';
            const isOpen = openCustom === h.hosting_id;

            return (
              <div key={h.hosting_id} style={{ background: '#111', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, overflow: 'hidden' }}>
                {/* Main domain row */}
                <div style={{ padding: '20px 24px', display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: 'rgba(0,255,136,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <Globe size={18} color="#00ff88" />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>{h.name}</span>
                      <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: `${statusColor}18`, color: statusColor }}>
                        ● {h.status}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: '#888', fontFamily: 'monospace' }}>{displayUrl}</div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <CopyBtn text={url} />
                    <a href={url} target="_blank" rel="noreferrer" style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', color: '#888', display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, textDecoration: 'none' }}>
                      <ExternalLink size={11} /> Abrir
                    </a>
                  </div>
                </div>

                {/* Custom domain toggle */}
                <div
                  style={{ padding: '12px 24px', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', background: isOpen ? 'rgba(255,255,255,0.02)' : 'transparent', transition: 'background 0.15s' }}
                  onClick={() => setOpenCustom(isOpen ? null : h.hosting_id)}
                >
                  <span style={{ fontSize: 12, color: '#888', fontWeight: 600 }}>Conectar dominio propio</span>
                  {isOpen ? <ChevronUp size={14} color="#666" /> : <ChevronDown size={14} color="#666" />}
                </div>

                {isOpen && (
                  <div style={{ padding: '0 24px 24px', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                    {/* DNS instructions */}
                    <div style={{ background: 'rgba(96,165,250,0.06)', border: '1px solid rgba(96,165,250,0.15)', borderRadius: 10, padding: 14, marginBottom: 16, marginTop: 16 }}>
                      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                        <Info size={14} color="#60a5fa" style={{ flexShrink: 0, marginTop: 1 }} />
                        <span style={{ fontSize: 12, color: '#60a5fa', fontWeight: 700 }}>Configuración DNS requerida</span>
                      </div>
                      <div style={{ fontSize: 11, color: '#888', lineHeight: 1.7 }}>
                        En tu proveedor de dominio, agregá los siguientes registros DNS:
                      </div>
                      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {[
                          { type: 'CNAME', name: 'www', value: 'hostingguard.lat' },
                          { type: 'A', name: '@', value: '45.55.128.10' },
                        ].map((r, i) => (
                          <div key={i} style={{ display: 'flex', gap: 8, fontFamily: 'monospace', fontSize: 11, background: 'rgba(0,0,0,0.3)', borderRadius: 6, padding: '6px 10px' }}>
                            <span style={{ color: '#00ff88', minWidth: 48 }}>{r.type}</span>
                            <span style={{ color: '#888', minWidth: 32 }}>{r.name}</span>
                            <span style={{ color: '#ccc' }}>{r.value}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: 10 }}>
                      <input
                        value={customDomain}
                        onChange={e => setCustomDomain(e.target.value)}
                        placeholder="tudominio.com"
                        style={{ flex: 1, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '8px 12px', color: '#fff', fontSize: 13, outline: 'none', fontFamily: 'monospace' }}
                      />
                      <button style={{ background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.2)', borderRadius: 8, padding: '8px 16px', color: '#00ff88', fontSize: 12, fontWeight: 700, cursor: 'pointer', opacity: 0.6 }}>
                        Próximamente
                      </button>
                    </div>
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

export default DomainsSection;
