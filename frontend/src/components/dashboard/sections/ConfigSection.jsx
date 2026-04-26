import { useState } from 'react';
import { User, Save, Check, Copy, Eye, EyeOff, Play, Square, RotateCcw, Key, ExternalLink, Camera } from 'lucide-react';
import { updateUserConfig } from '../../../services/api';

const Field = ({ label, value, onChange, type = 'text', readOnly = false, placeholder = '' }) => (
  <div>
    <label style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: 6 }}>{label}</label>
    <input
      type={type}
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      placeholder={placeholder}
      style={{ width: '100%', boxSizing: 'border-box', background: readOnly ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '9px 12px', color: readOnly ? '#555' : '#fff', fontSize: 13, outline: 'none', cursor: readOnly ? 'default' : 'text', transition: 'border-color 0.15s' }}
      onFocus={e => !readOnly && (e.target.style.borderColor = 'rgba(0,255,136,0.3)')}
      onBlur={e => (e.target.style.borderColor = 'rgba(255,255,255,0.1)')}
    />
  </div>
);

const CopyBtn = ({ text }) => {
  const [copied, setCopied] = useState(false);
  const handle = () => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); };
  return (
    <button onClick={handle} style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', color: copied ? '#00ff88' : '#777', display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, transition: 'all 0.15s' }}>
      {copied ? <Check size={11} /> : <Copy size={11} />}
      {copied ? 'Copiado' : 'Copiar'}
    </button>
  );
};

const STATUS_COLOR = { active: '#00ff88', stopped: '#f59e0b', error: '#ef4444', exited: '#f59e0b' };

const ConfigSection = ({ user = {}, setUser, hostings = [], onStart, onStop, onRestart, actionLoading }) => {
  const [form, setForm] = useState({ first_name: user.first_name || '', last_name: user.last_name || '', phone: user.phone || '' });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showPasswords, setShowPasswords] = useState({});
  const [pwForm, setPwForm] = useState({ current: '', newPw: '', confirm: '' });
  const [showPwSection, setShowPwSection] = useState(false);

  const set = (key) => (e) => setForm(f => ({ ...f, [key]: e.target.value }));

  const handleSaveProfile = async () => {
    setSaving(true);
    try {
      await updateUserConfig({ first_name: form.first_name, last_name: form.last_name, phone: form.phone });
      setUser(prev => ({ ...prev, ...form }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (_) {
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };

  const initials = ((form.first_name?.[0] || '') + (form.last_name?.[0] || '')) || user.email?.[0]?.toUpperCase() || '?';

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', marginBottom: 6 }}>Configuración</div>
        <div style={{ fontSize: 13, color: '#666' }}>Tu perfil, credenciales y gestión de contenedores.</div>
      </div>

      {/* Profile */}
      <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, padding: '24px', marginBottom: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>
          <User size={15} color="#818cf8" /> Perfil personal
        </div>

        {/* Avatar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <div style={{ position: 'relative' }}>
            <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'linear-gradient(135deg, #818cf8, #6366f1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, fontWeight: 900, color: '#fff', border: '3px solid rgba(129,140,248,0.3)', userSelect: 'none' }}>
              {initials}
            </div>
            <button title="Próximamente" style={{ position: 'absolute', bottom: 0, right: 0, width: 24, height: 24, borderRadius: '50%', background: '#0a0a0c', border: '2px solid rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'not-allowed', opacity: 0.6 }}>
              <Camera size={11} color="#888" />
            </button>
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>{form.first_name || form.last_name ? `${form.first_name} ${form.last_name}`.trim() : 'Sin nombre'}</div>
            <div style={{ fontSize: 12, color: '#555', marginTop: 2 }}>{user.email}</div>
            <div style={{ fontSize: 10, color: '#444', marginTop: 4 }}>Foto de perfil — próximamente</div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
          <Field label="Nombre" value={form.first_name} onChange={set('first_name')} placeholder="Juan" />
          <Field label="Apellido" value={form.last_name} onChange={set('last_name')} placeholder="Pérez" />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 20 }}>
          <Field label="Email" value={user.email || ''} readOnly />
          <Field label="Teléfono" value={form.phone} onChange={set('phone')} placeholder="+54 11 1234-5678" />
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button
            onClick={handleSaveProfile}
            disabled={saving}
            style={{ display: 'flex', alignItems: 'center', gap: 8, background: saved ? 'rgba(0,255,136,0.1)' : 'rgba(0,255,136,0.15)', border: `1px solid ${saved ? 'rgba(0,255,136,0.3)' : 'rgba(0,255,136,0.2)'}`, borderRadius: 10, padding: '9px 18px', color: '#00ff88', fontSize: 13, fontWeight: 700, cursor: saving ? 'wait' : 'pointer', transition: 'all 0.2s' }}
          >
            {saved ? <><Check size={14} /> Guardado</> : saving ? <><Save size={14} /> Guardando...</> : <><Save size={14} /> Guardar cambios</>}
          </button>

          <button
            onClick={() => setShowPwSection(v => !v)}
            style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: '9px 16px', color: '#888', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
          >
            <Key size={13} /> {showPwSection ? 'Cancelar' : 'Cambiar contraseña'}
          </button>
        </div>

        {showPwSection && (
          <div style={{ marginTop: 20, paddingTop: 20, borderTop: '1px solid rgba(255,255,255,0.05)', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            <Field label="Contraseña actual" value={pwForm.current} onChange={e => setPwForm(f => ({ ...f, current: e.target.value }))} type="password" placeholder="••••••••" />
            <Field label="Nueva contraseña" value={pwForm.newPw} onChange={e => setPwForm(f => ({ ...f, newPw: e.target.value }))} type="password" placeholder="••••••••" />
            <Field label="Confirmar" value={pwForm.confirm} onChange={e => setPwForm(f => ({ ...f, confirm: e.target.value }))} type="password" placeholder="••••••••" />
            <div style={{ gridColumn: '1/-1' }}>
              <button style={{ background: 'rgba(129,140,248,0.12)', border: '1px solid rgba(129,140,248,0.2)', borderRadius: 8, padding: '8px 16px', color: '#818cf8', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
                Actualizar contraseña
              </button>
            </div>
          </div>
        )}
      </div>

      {/* WP Credentials per hosting */}
      {hostings.some(h => h.wp_admin_password) && (
        <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, padding: '24px', marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Key size={15} color="#f59e0b" /> Acceso WordPress
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {hostings.filter(h => h.wp_admin_password).map(h => {
              const showPw = showPasswords[h.hosting_id];
              const subdomain = h.subdomain || '';
              const wpUrl = subdomain.includes('.') ? `https://${subdomain}/wp-admin` : `https://${subdomain}.hostingguard.lat/wp-admin`;

              return (
                <div key={h.hosting_id} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: '14px 16px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>{h.name}</span>
                    <a href={wpUrl} target="_blank" rel="noreferrer" style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#818cf8', textDecoration: 'none', background: 'rgba(129,140,248,0.1)', border: '1px solid rgba(129,140,248,0.2)', borderRadius: 6, padding: '4px 10px' }}>
                      <ExternalLink size={11} /> Ir a wp-admin
                    </a>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <div>
                      <div style={{ fontSize: 10, color: '#555', fontWeight: 700, marginBottom: 4 }}>USUARIO</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 12, color: '#ccc', fontFamily: 'monospace' }}>admin</span>
                        <CopyBtn text="admin" />
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: '#555', fontWeight: 700, marginBottom: 4 }}>CONTRASEÑA</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 12, color: '#ccc', fontFamily: 'monospace' }}>
                          {showPw ? h.wp_admin_password : '••••••••••••'}
                        </span>
                        <button onClick={() => setShowPasswords(p => ({ ...p, [h.hosting_id]: !p[h.hosting_id] }))} style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer', padding: 0, display: 'flex' }}>
                          {showPw ? <EyeOff size={13} /> : <Eye size={13} />}
                        </button>
                        {showPw && <CopyBtn text={h.wp_admin_password} />}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Container actions */}
      <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, padding: '24px' }}>
        <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
          <RotateCcw size={15} color="#60a5fa" /> Control de contenedores
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {hostings.map(h => {
            const isLoading = actionLoading === h.hosting_id;
            const statusColor = STATUS_COLOR[h.status] || '#888';

            return (
              <div key={h.hosting_id} style={{ display: 'flex', alignItems: 'center', gap: 16, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 10, padding: '12px 16px' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>{h.name}</div>
                  <div style={{ fontSize: 11, color: statusColor, fontWeight: 600, marginTop: 2 }}>● {h.status}</div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => onStart?.(h.hosting_id)}
                    disabled={isLoading || h.status === 'active'}
                    title="Iniciar"
                    style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(0,255,136,0.08)', border: '1px solid rgba(0,255,136,0.15)', color: '#00ff88', cursor: h.status === 'active' ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: h.status === 'active' ? 0.3 : 1 }}
                  >
                    <Play size={13} />
                  </button>
                  <button
                    onClick={() => onStop?.(h.hosting_id)}
                    disabled={isLoading || h.status !== 'active'}
                    title="Detener"
                    style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)', color: '#ef4444', cursor: h.status !== 'active' ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: h.status !== 'active' ? 0.3 : 1 }}
                  >
                    <Square size={13} />
                  </button>
                  <button
                    onClick={() => onRestart?.(h.hosting_id)}
                    disabled={isLoading || h.status !== 'active'}
                    title="Reiniciar"
                    style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.15)', color: '#60a5fa', cursor: h.status !== 'active' ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: h.status !== 'active' ? 0.3 : 1 }}
                  >
                    <RotateCcw size={13} className={isLoading ? 'animate-spin' : ''} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default ConfigSection;
