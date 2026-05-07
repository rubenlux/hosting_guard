import { useState, useEffect, useCallback } from 'react';
import {
  Globe, Copy, Check, ExternalLink, ChevronDown, ChevronUp,
  Plus, Trash2, RefreshCw, Star, AlertTriangle, Info, Loader2, X,
} from 'lucide-react';
import { getDomains, addDomain, deleteDomain, verifyDomain, setPrimaryDomain } from '../../../services/api';

const CopyBtn = ({ text }) => {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button
      onClick={handle}
      style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, padding: '3px 8px', cursor: 'pointer', color: copied ? '#00ff88' : '#888', display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, transition: 'all 0.15s' }}
    >
      {copied ? <Check size={11} /> : <Copy size={11} />}
      {copied ? 'Copiado' : 'Copiar'}
    </button>
  );
};

const DNS_STATUS_BADGE = {
  pending:  { label: 'Pendiente', color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
  active:   { label: 'Activo',    color: '#00ff88', bg: 'rgba(0,255,136,0.08)' },
  failed:   { label: 'Error',     color: '#ef4444', bg: 'rgba(239,68,68,0.1)' },
};

const SSL_STATUS_BADGE = {
  pending:  { label: 'SSL pendiente', color: '#f59e0b' },
  active:   { label: 'SSL activo',    color: '#00ff88' },
  failed:   { label: 'SSL error',     color: '#ef4444' },
};

function DomainManager({ hosting }) {
  const [domains, setDomains]         = useState([]);
  const [loading, setLoading]         = useState(true);
  const [adding, setAdding]           = useState(false);
  const [newDomain, setNewDomain]     = useState('');
  const [addError, setAddError]       = useState('');
  const [verifying, setVerifying]     = useState({});
  const [deleting, setDeleting]       = useState({});
  const [instructions, setInstructions] = useState(null);

  const subdomain = hosting.subdomain || '';
  const subdomainFull = subdomain.includes('.') ? subdomain : `${subdomain}.hostingguard.lat`;

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getDomains(hosting.hosting_id);
      setDomains(data.domains || []);
    } catch {
      setDomains([]);
    } finally {
      setLoading(false);
    }
  }, [hosting.hosting_id]);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async () => {
    const raw = newDomain.trim().toLowerCase();
    if (!raw) return;
    setAddError('');
    setAdding(true);
    try {
      const result = await addDomain(hosting.hosting_id, raw);
      setNewDomain('');
      setInstructions(result.instructions);
      await load();
    } catch (err) {
      setAddError(err?.response?.data?.detail || 'Error al agregar el dominio');
    } finally {
      setAdding(false);
    }
  };

  const handleVerify = async (domainId) => {
    setVerifying(v => ({ ...v, [domainId]: true }));
    try {
      const result = await verifyDomain(hosting.hosting_id, domainId);
      if (!result.ok && result.instructions) {
        setInstructions(result.instructions);
      }
      await load();
    } catch {
      // silent
    } finally {
      setVerifying(v => ({ ...v, [domainId]: false }));
    }
  };

  const handleDelete = async (domainId) => {
    setDeleting(d => ({ ...d, [domainId]: true }));
    try {
      await deleteDomain(hosting.hosting_id, domainId);
      await load();
    } catch {
      // silent
    } finally {
      setDeleting(d => ({ ...d, [domainId]: false }));
    }
  };

  const handleSetPrimary = async (domainId) => {
    try {
      await setPrimaryDomain(hosting.hosting_id, domainId);
      await load();
    } catch {
      // silent
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '24px 0', display: 'flex', alignItems: 'center', gap: 8, color: '#555' }}>
        <Loader2 size={14} className="animate-spin" /> Cargando dominios...
      </div>
    );
  }

  return (
    <div style={{ paddingTop: 16 }}>
      {/* DNS instructions panel */}
      {instructions && (
        <div style={{ background: 'rgba(96,165,250,0.06)', border: '1px solid rgba(96,165,250,0.18)', borderRadius: 10, padding: 14, marginBottom: 16, position: 'relative' }}>
          <button onClick={() => setInstructions(null)} style={{ position: 'absolute', top: 10, right: 10, background: 'none', border: 'none', cursor: 'pointer', color: '#555' }}>
            <X size={13} />
          </button>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10, alignItems: 'center' }}>
            <Info size={13} color="#60a5fa" />
            <span style={{ fontSize: 12, color: '#60a5fa', fontWeight: 700 }}>Configurá el DNS en tu proveedor</span>
          </div>
          <div style={{ fontFamily: 'monospace', fontSize: 11, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', gap: 10, background: 'rgba(0,0,0,0.3)', borderRadius: 6, padding: '7px 10px' }}>
              <span style={{ color: '#00ff88', minWidth: 44 }}>{instructions.type}</span>
              <span style={{ color: '#888', minWidth: 28 }}>{instructions.name}</span>
              <span style={{ color: '#ccc', flex: 1 }}>{instructions.value}</span>
              <CopyBtn text={instructions.value} />
            </div>
          </div>
          <div style={{ fontSize: 11, color: '#666', marginTop: 10, lineHeight: 1.6 }}>{instructions.note}</div>
        </div>
      )}

      {/* Custom domains list */}
      {domains.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
          {domains.map(d => {
            const dnsBadge = DNS_STATUS_BADGE[d.dns_status] || DNS_STATUS_BADGE.pending;
            const sslBadge = d.ssl_status ? SSL_STATUS_BADGE[d.ssl_status] : null;
            return (
              <div key={d.domain_id} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 10, padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
                <Globe size={13} color={dnsBadge.color} style={{ flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 13, color: '#fff', fontFamily: 'monospace' }}>{d.domain}</span>
                    {d.is_primary === 1 && (
                      <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 20, background: 'rgba(0,255,136,0.1)', color: '#00ff88', fontWeight: 700 }}>Primario</span>
                    )}
                    <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 20, background: dnsBadge.bg, color: dnsBadge.color }}>{dnsBadge.label}</span>
                    {sslBadge && (
                      <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 20, background: 'rgba(255,255,255,0.05)', color: sslBadge.color }}>{sslBadge.label}</span>
                    )}
                  </div>
                  {d.error_message && (
                    <div style={{ fontSize: 11, color: '#ef4444', marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                      <AlertTriangle size={11} /> {d.error_message}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                  {d.dns_status !== 'active' && (
                    <button
                      onClick={() => handleVerify(d.domain_id)}
                      disabled={verifying[d.domain_id]}
                      style={{ background: 'rgba(96,165,250,0.1)', border: '1px solid rgba(96,165,250,0.2)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', color: '#60a5fa', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4, opacity: verifying[d.domain_id] ? 0.5 : 1 }}
                    >
                      {verifying[d.domain_id] ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                      Verificar
                    </button>
                  )}
                  {d.dns_status === 'active' && d.is_primary !== 1 && (
                    <button
                      onClick={() => handleSetPrimary(d.domain_id)}
                      style={{ background: 'rgba(0,255,136,0.08)', border: '1px solid rgba(0,255,136,0.15)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', color: '#00ff88', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}
                    >
                      <Star size={11} /> Primario
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(d.domain_id)}
                    disabled={deleting[d.domain_id]}
                    style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', color: '#ef4444', fontSize: 11, opacity: deleting[d.domain_id] ? 0.5 : 1 }}
                  >
                    {deleting[d.domain_id] ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add domain input */}
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          value={newDomain}
          onChange={e => { setNewDomain(e.target.value); setAddError(''); }}
          onKeyDown={e => e.key === 'Enter' && handleAdd()}
          placeholder="tudominio.com"
          style={{ flex: 1, background: 'rgba(255,255,255,0.04)', border: `1px solid ${addError ? 'rgba(239,68,68,0.4)' : 'rgba(255,255,255,0.1)'}`, borderRadius: 8, padding: '8px 12px', color: '#fff', fontSize: 13, outline: 'none', fontFamily: 'monospace' }}
        />
        <button
          onClick={handleAdd}
          disabled={adding || !newDomain.trim()}
          style={{ background: adding || !newDomain.trim() ? 'rgba(255,255,255,0.04)' : 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.2)', borderRadius: 8, padding: '8px 14px', cursor: adding || !newDomain.trim() ? 'not-allowed' : 'pointer', color: '#00ff88', fontSize: 12, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6, opacity: adding || !newDomain.trim() ? 0.4 : 1, whiteSpace: 'nowrap' }}
        >
          {adding ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
          Agregar
        </button>
      </div>
      {addError && (
        <div style={{ marginTop: 8, fontSize: 12, color: '#ef4444', display: 'flex', alignItems: 'center', gap: 6 }}>
          <AlertTriangle size={12} /> {addError}
        </div>
      )}
      <div style={{ marginTop: 10, fontSize: 11, color: '#555', lineHeight: 1.6 }}>
        Después de agregar el dominio, configurá el DNS en tu proveedor apuntando a <span style={{ color: '#888', fontFamily: 'monospace' }}>{subdomainFull}</span> y luego hacé clic en Verificar.
      </div>
    </div>
  );
}

const STATUS_COLOR = { active: '#00ff88', stopped: '#f59e0b', error: '#ef4444', exited: '#f59e0b' };

const DomainsSection = ({ hostings = [] }) => {
  const [openId, setOpenId] = useState(null);

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
            const subdomain   = h.subdomain || '';
            const url         = subdomain.includes('.') ? `https://${subdomain}` : `https://${subdomain}.hostingguard.lat`;
            const displayUrl  = subdomain.includes('.') ? subdomain : `${subdomain}.hostingguard.lat`;
            const statusColor = STATUS_COLOR[h.status] || '#888';
            const isOpen      = openId === h.hosting_id;

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
                        {h.status}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: '#888', fontFamily: 'monospace' }}>{displayUrl}</div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <CopyBtn text={url} />
                    <a href={url} target="_blank" rel="noreferrer" style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, padding: '4px 10px', color: '#888', display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, textDecoration: 'none' }}>
                      <ExternalLink size={11} /> Abrir
                    </a>
                  </div>
                </div>

                {/* Custom domain toggle */}
                <div
                  onClick={() => setOpenId(isOpen ? null : h.hosting_id)}
                  style={{ padding: '12px 24px', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', background: isOpen ? 'rgba(255,255,255,0.02)' : 'transparent', transition: 'background 0.15s' }}
                >
                  <span style={{ fontSize: 12, color: '#888', fontWeight: 600 }}>Conectar dominio propio</span>
                  {isOpen ? <ChevronUp size={14} color="#666" /> : <ChevronDown size={14} color="#666" />}
                </div>

                {isOpen && (
                  <div style={{ padding: '0 24px 24px', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                    <DomainManager hosting={h} />
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
