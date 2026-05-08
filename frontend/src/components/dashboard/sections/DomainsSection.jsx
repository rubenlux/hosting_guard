import { useState, useEffect, useCallback } from 'react';
import {
  Globe, Copy, Check, ExternalLink, ChevronDown, ChevronUp,
  Plus, Trash2, RefreshCw, Star, AlertTriangle, Info,
  Loader2, X, ShieldCheck, Clock, CheckCircle2, XCircle,
} from 'lucide-react';
import { getDomains, addDomain, deleteDomain, verifyDomain, setPrimaryDomain } from '../../../services/api';

// ── helpers ───────────────────────────────────────────────────────────────────

function isApex(domain) {
  const d = domain.trim().toLowerCase().replace(/\.$/, '');
  return d.split('.').length === 2;
}

function subLabel(domain) {
  const parts = domain.trim().toLowerCase().split('.');
  if (parts.length === 2) return '@';
  return parts.slice(0, parts.length - 2).join('.');
}

function cleanValue(v) {
  return (v || '').replace(/\.$/, '');
}

// ── CopyBtn ───────────────────────────────────────────────────────────────────

function CopyBtn({ text, label = 'Copiar' }) {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };
  return (
    <button onClick={handle} style={{
      display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 10px',
      background: copied ? 'rgba(0,255,136,0.1)' : 'rgba(255,255,255,0.06)',
      border: `1px solid ${copied ? 'rgba(0,255,136,0.3)' : 'rgba(255,255,255,0.1)'}`,
      borderRadius: 6, cursor: 'pointer', color: copied ? '#00ff88' : '#aaa',
      fontSize: 11, fontWeight: 600, transition: 'all 0.15s', whiteSpace: 'nowrap',
    }}>
      {copied ? <Check size={11} /> : <Copy size={11} />}
      {copied ? 'Copiado' : label}
    </button>
  );
}

// ── DNS table ─────────────────────────────────────────────────────────────────

function DnsTable({ instructions, subdomainFull }) {
  if (!instructions) return null;
  const host  = instructions.type === 'A' ? '@' : subLabel(instructions.name || '');
  const value = cleanValue(instructions.value);
  const isA   = instructions.type === 'A';

  return (
    <div style={{
      background: 'rgba(0,0,0,0.35)', border: '1px solid rgba(255,255,255,0.08)',
      borderRadius: 10, overflow: 'hidden', marginBottom: 12,
    }}>
      {/* header */}
      <div style={{
        padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,0.06)',
        display: 'flex', alignItems: 'center', gap: 8,
        background: isA ? 'rgba(249,115,22,0.06)' : 'rgba(96,165,250,0.06)',
      }}>
        <Info size={13} color={isA ? '#f97316' : '#60a5fa'} />
        <span style={{ fontSize: 12, fontWeight: 700, color: isA ? '#f97316' : '#60a5fa' }}>
          {isA ? 'Registro A — para dominio raíz' : 'Registro CNAME — para subdominio'}
        </span>
      </div>

      {/* column headers */}
      <div style={{
        display: 'grid', gridTemplateColumns: '80px 100px 1fr 60px',
        padding: '7px 14px', borderBottom: '1px solid rgba(255,255,255,0.04)',
        fontSize: 10, color: '#555', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em',
      }}>
        <span>Tipo</span><span>Host/Nombre</span><span>Valor/Destino</span><span>TTL</span>
      </div>

      {/* values */}
      <div style={{
        display: 'grid', gridTemplateColumns: '80px 100px 1fr 60px',
        padding: '10px 14px', alignItems: 'center', gap: 6,
      }}>
        <span style={{ fontFamily: 'monospace', fontSize: 13, fontWeight: 800, color: isA ? '#f97316' : '#60a5fa' }}>
          {instructions.type}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#ddd' }}>{host}</span>
          <CopyBtn text={host} label="Copiar" />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#fff', wordBreak: 'break-all' }}>{value}</span>
          <CopyBtn text={value} label="Copiar" />
        </div>
        <span style={{ fontSize: 12, color: '#555' }}>Auto</span>
      </div>

      {/* note */}
      <div style={{
        padding: '8px 14px', borderTop: '1px solid rgba(255,255,255,0.04)',
        fontSize: 11, color: '#666', lineHeight: 1.6,
        background: 'rgba(255,255,255,0.02)',
      }}>
        {isA
          ? `Creá un registro A con nombre @ y el valor ${value}. Si tu proveedor no acepta @, usá el dominio raíz directamente.`
          : `Creá un registro CNAME con nombre ${host} apuntando a ${value}. No incluyas el nombre del dominio en el valor.`}
      </div>
    </div>
  );
}

// ── DNS status stepper ────────────────────────────────────────────────────────

function StatusStepper({ dns_status, ssl_status }) {
  const steps = [
    {
      key: 'dns',
      label: 'DNS',
      status: dns_status,
      desc: { active: 'Verificado', pending: 'Verificando...', failed: 'Error' },
    },
    {
      key: 'ssl',
      label: 'SSL',
      status: ssl_status || 'pending',
      desc: { active: 'Activo', pending: 'Emitiendo...', failed: 'Error' },
    },
    {
      key: 'done',
      label: 'Activo',
      status: dns_status === 'active' && ssl_status === 'active' ? 'active' : 'pending',
      desc: { active: 'Listo', pending: 'Esperando' },
    },
  ];
  const colors = { active: '#00ff88', pending: '#f59e0b', failed: '#ef4444' };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      {steps.map((s, i) => {
        const c = colors[s.status] || '#555';
        return (
          <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%', border: `2px solid ${c}`,
                background: s.status === 'active' ? `${c}18` : 'transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {s.status === 'active'
                  ? <CheckCircle2 size={13} color={c} />
                  : s.status === 'failed'
                    ? <XCircle size={13} color={c} />
                    : <Clock size={11} color={c} />}
              </div>
              <span style={{ fontSize: 9, color: c, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {s.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div style={{ width: 24, height: 1, background: 'rgba(255,255,255,0.1)', marginBottom: 10 }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── DomainCard ────────────────────────────────────────────────────────────────

function DomainCard({ domain: d, hostingId, subdomainFull, onRefresh }) {
  const [verifying, setVerifying] = useState(false);
  const [deleting,  setDeleting]  = useState(false);
  const [showDns,   setShowDns]   = useState(d.dns_status !== 'active');
  const [verifyResult, setVerifyResult] = useState(null);

  const apex    = isApex(d.domain);
  const isPrimary = d.is_primary === 1;

  // build DNS instructions from stored domain type + subdomainFull
  const dnsInstructions = {
    type:  apex ? 'A' : 'CNAME',
    name:  d.domain,
    value: apex ? (d.server_ip || 'IP del servidor') : `${subdomainFull}.`,
  };

  const handleVerify = async () => {
    setVerifying(true);
    setVerifyResult(null);
    try {
      const res = await verifyDomain(hostingId, d.domain_id);
      setVerifyResult(res);
      if (res.ok) setShowDns(false);
      await onRefresh();
    } catch (err) {
      setVerifyResult({ ok: false, error: err?.response?.data?.detail || 'Error al verificar' });
    } finally {
      setVerifying(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`¿Eliminar el dominio ${d.domain}?`)) return;
    setDeleting(true);
    try {
      await deleteDomain(hostingId, d.domain_id);
      await onRefresh();
    } catch {
      setDeleting(false);
    }
  };

  const handleSetPrimary = async () => {
    try {
      await setPrimaryDomain(hostingId, d.domain_id);
      await onRefresh();
    } catch {/* silent */}
  };

  const dnsOk  = d.dns_status === 'active';
  const sslOk  = d.ssl_status === 'active';
  const failed = d.dns_status === 'failed';
  const borderColor = dnsOk && sslOk ? 'rgba(0,255,136,0.2)' : failed ? 'rgba(239,68,68,0.2)' : 'rgba(255,255,255,0.08)';

  return (
    <div style={{
      background: '#111', border: `1px solid ${borderColor}`,
      borderRadius: 12, overflow: 'hidden', marginBottom: 10,
    }}>
      {/* Card header */}
      <div style={{ padding: '14px 16px', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#fff', fontFamily: 'monospace' }}>
              {d.domain}
            </span>
            <span style={{
              fontSize: 10, padding: '2px 7px', borderRadius: 20, fontWeight: 700,
              background: apex ? 'rgba(249,115,22,0.1)' : 'rgba(96,165,250,0.1)',
              color: apex ? '#f97316' : '#60a5fa',
            }}>
              {apex ? 'Dominio raíz' : 'Subdominio'}
            </span>
            {isPrimary && (
              <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 20, background: 'rgba(0,255,136,0.1)', color: '#00ff88', fontWeight: 700 }}>
                ★ Primario
              </span>
            )}
          </div>
          <StatusStepper dns_status={d.dns_status} ssl_status={d.ssl_status} />
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 6, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {!dnsOk && (
            <button onClick={handleVerify} disabled={verifying} style={{
              display: 'flex', alignItems: 'center', gap: 5, padding: '6px 12px',
              background: 'rgba(96,165,250,0.1)', border: '1px solid rgba(96,165,250,0.25)',
              borderRadius: 8, cursor: verifying ? 'wait' : 'pointer', color: '#60a5fa',
              fontSize: 12, fontWeight: 700, opacity: verifying ? 0.6 : 1,
            }}>
              {verifying ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              {verifying ? 'Verificando...' : 'Ya configuré mi DNS, verificar ahora'}
            </button>
          )}
          {dnsOk && !isPrimary && (
            <button onClick={handleSetPrimary} style={{
              display: 'flex', alignItems: 'center', gap: 5, padding: '6px 10px',
              background: 'rgba(0,255,136,0.08)', border: '1px solid rgba(0,255,136,0.2)',
              borderRadius: 8, cursor: 'pointer', color: '#00ff88', fontSize: 12, fontWeight: 700,
            }}>
              <Star size={12} /> Hacer primario
            </button>
          )}
          <button onClick={handleDelete} disabled={deleting} style={{
            display: 'flex', alignItems: 'center', gap: 4, padding: '6px 10px',
            background: 'rgba(239,68,68,0.07)', border: '1px solid rgba(239,68,68,0.15)',
            borderRadius: 8, cursor: deleting ? 'wait' : 'pointer', color: '#ef4444',
            fontSize: 12, fontWeight: 600, opacity: deleting ? 0.5 : 1,
          }}>
            {deleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
            Eliminar
          </button>
        </div>
      </div>

      {/* Verification error result */}
      {verifyResult && !verifyResult.ok && (
        <div style={{
          margin: '0 16px 12px', padding: '10px 14px',
          background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)',
          borderRadius: 8,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <AlertTriangle size={13} color="#ef4444" />
            <span style={{ fontSize: 12, fontWeight: 700, color: '#ef4444' }}>No pudimos verificar el DNS todavía</span>
          </div>
          <div style={{ fontSize: 12, color: '#aaa', lineHeight: 1.7 }}>
            {verifyResult.error}
          </div>
          {verifyResult.resolved_ip && (
            <div style={{ marginTop: 8, fontSize: 11, color: '#888' }}>
              <span style={{ color: '#f59e0b' }}>Detectamos: </span>
              <span style={{ fontFamily: 'monospace' }}>{verifyResult.resolved_ip}</span>
              {' — '}revisá que el registro DNS esté bien configurado.
            </div>
          )}
          <div style={{ marginTop: 6, fontSize: 11, color: '#555' }}>
            Los cambios DNS pueden tardar desde algunos minutos hasta 24 horas en propagarse.
          </div>
        </div>
      )}

      {/* Stored error message (from scheduler check) */}
      {!verifyResult && d.error_message && !dnsOk && (
        <div style={{
          margin: '0 16px 12px', padding: '10px 14px',
          background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)',
          borderRadius: 8,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <AlertTriangle size={13} color="#f59e0b" />
            <span style={{ fontSize: 12, fontWeight: 700, color: '#f59e0b' }}>Último intento de verificación</span>
          </div>
          <div style={{ fontSize: 12, color: '#aaa', lineHeight: 1.7 }}>{d.error_message}</div>
          <div style={{ marginTop: 6, fontSize: 11, color: '#555' }}>
            Los cambios DNS pueden tardar desde algunos minutos hasta 24 horas en propagarse.
          </div>
        </div>
      )}

      {/* DNS instructions */}
      {!dnsOk && (
        <div style={{ padding: '0 16px 14px' }}>
          <button
            onClick={() => setShowDns(v => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, marginBottom: showDns ? 10 : 0,
              background: 'none', border: 'none', cursor: 'pointer', color: '#60a5fa',
              fontSize: 12, fontWeight: 600, padding: 0,
            }}
          >
            {showDns ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            {showDns ? 'Ocultar instrucciones DNS' : 'Ver instrucciones DNS'}
          </button>

          {showDns && (
            <DnsTable instructions={dnsInstructions} subdomainFull={subdomainFull} />
          )}
        </div>
      )}

      {/* Active: success message */}
      {dnsOk && sslOk && (
        <div style={{
          margin: '0 16px 14px', padding: '10px 14px',
          background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.15)',
          borderRadius: 8, display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <ShieldCheck size={14} color="#00ff88" />
          <span style={{ fontSize: 12, color: '#00ff88', fontWeight: 600 }}>
            Dominio activo con SSL. Tu sitio es accesible en https://{d.domain}
          </span>
          <div style={{ marginLeft: 'auto' }}>
            <a href={`https://${d.domain}`} target="_blank" rel="noreferrer" style={{
              display: 'flex', alignItems: 'center', gap: 4,
              color: '#555', fontSize: 11, textDecoration: 'none',
            }}>
              <ExternalLink size={11} /> Abrir
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

// ── DomainManager (per hosting) ───────────────────────────────────────────────

function DomainManager({ hosting }) {
  const [domains,   setDomains]   = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [adding,    setAdding]    = useState(false);
  const [newDomain, setNewDomain] = useState('');
  const [addError,  setAddError]  = useState('');
  const [addedInstructions, setAddedInstructions] = useState(null);

  const subdomain     = hosting.subdomain || '';
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

  const previewType = newDomain.trim() ? (isApex(newDomain.trim()) ? 'apex' : 'subdomain') : null;

  const handleAdd = async () => {
    const raw = newDomain.trim().toLowerCase();
    if (!raw) return;
    setAddError('');
    setAdding(true);
    try {
      const result = await addDomain(hosting.hosting_id, raw);
      setNewDomain('');
      setAddedInstructions(result.instructions);
      await load();
    } catch (err) {
      setAddError(err?.response?.data?.detail || 'Error al agregar el dominio');
    } finally {
      setAdding(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '20px 0', display: 'flex', alignItems: 'center', gap: 8, color: '#555', fontSize: 12 }}>
        <Loader2 size={13} className="animate-spin" /> Cargando dominios...
      </div>
    );
  }

  return (
    <div style={{ paddingTop: 16 }}>

      {/* Temporary subdomain pill */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16,
        padding: '8px 12px', borderRadius: 8,
        background: 'rgba(0,255,136,0.05)', border: '1px solid rgba(0,255,136,0.12)',
      }}>
        <Globe size={12} color="#00ff88" style={{ flexShrink: 0 }} />
        <span style={{ fontSize: 11, color: '#555' }}>Dominio temporal:</span>
        <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#00ff88' }}>{subdomainFull}</span>
      </div>

      {/* Existing domains */}
      {domains.map(d => (
        <DomainCard
          key={d.domain_id}
          domain={d}
          hostingId={hosting.hosting_id}
          subdomainFull={subdomainFull}
          onRefresh={load}
        />
      ))}

      {/* Add domain panel */}
      <div style={{
        background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 12, overflow: 'hidden', marginTop: domains.length ? 8 : 0,
      }}>

        {/* ── 3-step mini guide ── */}
        <div style={{
          padding: '18px 18px 16px',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
        }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#ccc', marginBottom: 14 }}>
            Conectar tu dominio en 3 pasos
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[
              {
                n: '1',
                title: 'Agregá tu dominio',
                body: 'Puede ser tu dominio principal, como ejemplo.com, o un subdominio, como www.ejemplo.com.',
                color: '#60a5fa',
              },
              {
                n: '2',
                title: 'Copiá el registro DNS',
                body: 'Después de agregarlo, te mostramos exactamente qué registro crear en el panel de tu proveedor.',
                color: '#a78bfa',
              },
              {
                n: '3',
                title: 'Verificá y activá SSL',
                body: 'Cuando el DNS apunte correctamente a HostingGuard, activamos HTTPS automáticamente.',
                color: '#00ff88',
              },
            ].map(({ n, title, body, color }) => (
              <div key={n} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <div style={{
                  width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                  background: `${color}15`, border: `1px solid ${color}30`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 10, fontWeight: 800, color,
                }}>
                  {n}
                </div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#bbb', marginBottom: 2 }}>{title}</div>
                  <div style={{ fontSize: 11, color: '#555', lineHeight: 1.65 }}>{body}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Note */}
          <div style={{
            marginTop: 14, padding: '10px 12px',
            background: 'rgba(255,255,255,0.03)', borderRadius: 8,
            border: '1px solid rgba(255,255,255,0.06)',
          }}>
            <div style={{ fontSize: 11, color: '#555', lineHeight: 1.7 }}>
              <span style={{ color: '#777', fontWeight: 600 }}>No necesitás transferir tu dominio</span> ni cambiar de proveedor.
              Solo tenés que agregar el registro DNS indicado.
            </div>
          </div>

          {/* Where to configure */}
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#666', marginBottom: 5 }}>
              ¿Dónde configuro esto?
            </div>
            <div style={{ fontSize: 11, color: '#4a4a4a', lineHeight: 1.7 }}>
              En el panel donde compraste o administrás tu dominio:{' '}
              {['Cloudflare', 'GoDaddy', 'Namecheap', 'DonWeb', 'Nic Argentina', 'Hostinger'].map((p, i, arr) => (
                <span key={p}>
                  <span style={{ color: '#666' }}>{p}</span>
                  {i < arr.length - 1 ? ', ' : ' u otro proveedor.'}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* ── Input section ── */}
        <div style={{ padding: '14px 18px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#666', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {domains.length === 0 ? 'Tu dominio' : 'Agregar otro dominio'}
          </div>

          <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
            <div style={{ flex: 1 }}>
              <input
                value={newDomain}
                onChange={e => { setNewDomain(e.target.value); setAddError(''); setAddedInstructions(null); }}
                onKeyDown={e => e.key === 'Enter' && handleAdd()}
                placeholder="ejemplo.com"
                style={{
                  width: '100%', background: 'rgba(255,255,255,0.04)',
                  border: `1px solid ${addError ? 'rgba(239,68,68,0.4)' : 'rgba(255,255,255,0.1)'}`,
                  borderRadius: 8, padding: '9px 12px', color: '#fff', fontSize: 13,
                  outline: 'none', fontFamily: 'monospace', boxSizing: 'border-box',
                }}
              />
            </div>
            <button
              onClick={handleAdd}
              disabled={adding || !newDomain.trim()}
              style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '9px 16px',
                background: adding || !newDomain.trim() ? 'rgba(255,255,255,0.03)' : 'rgba(0,255,136,0.1)',
                border: '1px solid rgba(0,255,136,0.2)', borderRadius: 8,
                cursor: adding || !newDomain.trim() ? 'not-allowed' : 'pointer',
                color: '#00ff88', fontSize: 12, fontWeight: 700,
                opacity: adding || !newDomain.trim() ? 0.4 : 1, whiteSpace: 'nowrap',
              }}
            >
              {adding ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
              Agregar
            </button>
          </div>

          {/* Examples */}
          {!newDomain.trim() && !addError && !addedInstructions && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
              <span style={{ fontSize: 10, color: '#3a3a3a', fontWeight: 600 }}>Ejemplos válidos:</span>
              {['ejemplo.com', 'www.ejemplo.com', 'app.ejemplo.com'].map(ex => (
                <button
                  key={ex}
                  onClick={() => { setNewDomain(ex); setAddError(''); setAddedInstructions(null); }}
                  style={{
                    fontFamily: 'monospace', fontSize: 10, color: '#4a4a4a',
                    background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
                    borderRadius: 4, padding: '2px 7px', cursor: 'pointer',
                  }}
                >
                  {ex}
                </button>
              ))}
            </div>
          )}

          {/* Real-time type preview */}
          {previewType && !addError && (
            <div style={{ fontSize: 11, color: previewType === 'apex' ? '#f97316' : '#60a5fa', marginBottom: 4 }}>
              {previewType === 'apex'
                ? '→ Dominio raíz: vas a necesitar un registro A'
                : `→ Subdominio: vas a necesitar un registro CNAME apuntando a ${subdomainFull}`}
            </div>
          )}

          {addError && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#ef4444' }}>
              <AlertTriangle size={12} /> {addError}
            </div>
          )}

          {/* Instructions shown right after adding */}
          {addedInstructions && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12, color: '#aaa', marginBottom: 8, fontWeight: 600 }}>
                Paso 2 — Entrá al panel de tu proveedor de dominio y creá este registro:
              </div>
              <DnsTable instructions={addedInstructions} subdomainFull={subdomainFull} />
              <div style={{
                padding: '10px 12px', borderRadius: 8,
                background: 'rgba(96,165,250,0.05)', border: '1px solid rgba(96,165,250,0.12)',
                fontSize: 12, color: '#666', lineHeight: 1.7,
              }}>
                Cuando hayas guardado el registro, hacé clic en{' '}
                <strong style={{ color: '#60a5fa' }}>"Ya configuré mi DNS, verificar ahora"</strong>{' '}
                en la tarjeta de arriba.
                <br />
                <span style={{ fontSize: 11, color: '#444' }}>
                  Los cambios DNS pueden tardar desde algunos minutos hasta algunas horas en propagarse — es normal.
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── DomainsSection ────────────────────────────────────────────────────────────

const STATUS_COLOR = { active: '#00ff88', stopped: '#f59e0b', error: '#ef4444', exited: '#f59e0b' };

const DomainsSection = ({ hostings = [] }) => {
  const [openId, setOpenId] = useState(null);

  return (
    <div style={{ maxWidth: 820, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', marginBottom: 6 }}>Dominios</div>
        <div style={{ fontSize: 13, color: '#555' }}>
          Conectá tu propio dominio a cualquiera de tus sitios.
          No necesitás mover ni transferir nada — solo configurar el DNS.
        </div>
      </div>

      {hostings.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '4rem 2rem',
          background: '#111', borderRadius: 16, border: '1px dashed rgba(255,255,255,0.08)',
        }}>
          <Globe size={32} style={{ color: '#333', marginBottom: 12 }} />
          <div style={{ color: '#555', fontSize: 14 }}>No tenés sitios activos aún.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {hostings.map(h => {
            const subdomain  = h.subdomain || '';
            const displayUrl = subdomain.includes('.') ? subdomain : `${subdomain}.hostingguard.lat`;
            const url        = `https://${displayUrl}`;
            const statusColor = STATUS_COLOR[h.status] || '#666';
            const isOpen = openId === h.hosting_id;

            return (
              <div key={h.hosting_id} style={{
                background: '#111', border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: 16, overflow: 'hidden',
              }}>
                {/* Hosting header */}
                <div style={{ padding: '18px 22px', display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div style={{
                    width: 38, height: 38, borderRadius: 10, flexShrink: 0,
                    background: 'rgba(0,255,136,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Globe size={17} color="#00ff88" />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                      <span style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>{h.name}</span>
                      <span style={{
                        fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 20,
                        background: `${statusColor}15`, color: statusColor,
                      }}>
                        {h.status}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: '#555', fontFamily: 'monospace' }}>
                      Dominio temporal: {displayUrl}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <CopyBtn text={url} label="Copiar URL" />
                    <a href={url} target="_blank" rel="noreferrer" style={{
                      display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px',
                      background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)',
                      borderRadius: 6, color: '#888', fontSize: 11, textDecoration: 'none',
                    }}>
                      <ExternalLink size={11} /> Abrir
                    </a>
                  </div>
                </div>

                {/* Toggle */}
                <div
                  onClick={() => setOpenId(isOpen ? null : h.hosting_id)}
                  style={{
                    padding: '11px 22px', borderTop: '1px solid rgba(255,255,255,0.05)',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    cursor: 'pointer', transition: 'background 0.15s',
                    background: isOpen ? 'rgba(255,255,255,0.02)' : 'transparent',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Globe size={13} color="#555" />
                    <span style={{ fontSize: 12, color: '#777', fontWeight: 600 }}>
                      Conectar dominio propio
                    </span>
                  </div>
                  {isOpen ? <ChevronUp size={13} color="#555" /> : <ChevronDown size={13} color="#555" />}
                </div>

                {isOpen && (
                  <div style={{ padding: '0 22px 22px', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
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
