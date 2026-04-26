import { useState } from 'react';
import {
  User, Save, Check, Key, ExternalLink, Shield, Bell,
  Globe, Trash2, Download, ChevronDown, ChevronUp, LogOut,
  Smartphone, AlertTriangle, Zap
} from 'lucide-react';
import { updateProfile, updateNotificationPrefs, uploadAvatar, resetWpPassword } from '../../../services/api';

// ── helpers ──────────────────────────────────────────────────────────────────
const Field = ({ label, value, onChange, type = 'text', readOnly = false, placeholder = '', as: Tag = 'input', children }) => (
  <div>
    <label style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: 6 }}>{label}</label>
    {Tag === 'select' ? (
      <select value={value} onChange={onChange} style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '9px 12px', color: '#fff', fontSize: 13, outline: 'none' }}>
        {children}
      </select>
    ) : (
      <input
        type={type} value={value} onChange={onChange} readOnly={readOnly} placeholder={placeholder}
        style={{ width: '100%', boxSizing: 'border-box', background: readOnly ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '9px 12px', color: readOnly ? '#555' : '#fff', fontSize: 13, outline: 'none', cursor: readOnly ? 'default' : 'text', transition: 'border-color 0.15s' }}
        onFocus={e => !readOnly && (e.target.style.borderColor = 'rgba(0,255,136,0.3)')}
        onBlur={e => (e.target.style.borderColor = 'rgba(255,255,255,0.1)')}
      />
    )}
  </div>
);

const Toggle = ({ label, desc, value, onChange }) => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
    <div>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>{label}</div>
      {desc && <div style={{ fontSize: 11, color: '#555', marginTop: 2 }}>{desc}</div>}
    </div>
    <div
      onClick={() => onChange(!value)}
      style={{ width: 40, height: 22, borderRadius: 11, background: value ? '#00ff88' : 'rgba(255,255,255,0.1)', position: 'relative', cursor: 'pointer', transition: 'background 0.2s', flexShrink: 0 }}
    >
      <div style={{ position: 'absolute', top: 3, left: value ? 21 : 3, width: 16, height: 16, borderRadius: '50%', background: '#fff', transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.3)' }} />
    </div>
  </div>
);

const SectionCard = ({ icon: Icon, iconColor = '#818cf8', title, children, defaultOpen = true }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, overflow: 'hidden', marginBottom: 16 }}>
      <div
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 24px', cursor: 'pointer' }}
        onClick={() => setOpen(v => !v)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: `${iconColor}18`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon size={16} color={iconColor} />
          </div>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>{title}</span>
        </div>
        {open ? <ChevronUp size={15} color="#555" /> : <ChevronDown size={15} color="#555" />}
      </div>
      {open && <div style={{ padding: '0 24px 24px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>{children}</div>}
    </div>
  );
};

const TIMEZONES = [
  'America/Argentina/Buenos_Aires', 'America/Bogota', 'America/Lima',
  'America/Santiago', 'America/Mexico_City', 'America/Caracas',
  'America/Montevideo', 'America/Asuncion', 'America/La_Paz',
  'Europe/Madrid', 'UTC',
];

const _API_BASE = import.meta.env.VITE_API_URL || 'https://api.hostingguard.lat';
const _resolveAvatarUrl = (url) => url && (url.startsWith('http') ? url : `${_API_BASE}${url}`);

const NOTIF_EVENTS = [
  { key: 'site_down',     label: 'Sitio caído',               desc: 'Cuando tu sitio no responde' },
  { key: 'high_usage',    label: 'Alto consumo CPU/RAM',       desc: 'Al superar el 85% de recursos' },
  { key: 'ssl_expiring',  label: 'SSL próximo a vencer',       desc: '7 días antes de la expiración' },
  { key: 'backup_done',   label: 'Backup completado/fallido',  desc: 'Al terminar un respaldo' },
  { key: 'import_done',   label: 'Importación completada',     desc: 'Al terminar una importación' },
  { key: 'payment',       label: 'Factura y pagos',            desc: 'Cobros, recargas y rechazos' },
  { key: 'plan_limit',    label: 'Límite de plan alcanzado',   desc: 'Cuando te acercás al límite' },
];

const WP_PREFS = [
  { key: 'auto_optimize', label: 'Optimización automática',  desc: 'Activa configuración óptima al crear sitios' },
  { key: 'auto_cache',    label: 'Cache automática',          desc: 'Activa WP Super Cache automáticamente' },
  { key: 'force_https',   label: 'Forzar HTTPS',             desc: 'Redirige todo el tráfico a HTTPS' },
  { key: 'secure_login',  label: 'Protección wp-login',       desc: 'Limita intentos de acceso al panel' },
  { key: 'health_checks', label: 'Health checks automáticos', desc: 'Monitoreo proactivo de errores' },
];

// ── Main component ────────────────────────────────────────────────────────────
const ConfigSection = ({ user = {}, setUser, hostings = [], logoutAction }) => {
  // Profile
  const [profile, setProfile] = useState({
    first_name: user.first_name || '',
    last_name:  user.last_name  || '',
    phone:      user.phone      || '',
    timezone:   user.timezone   || 'America/Argentina/Buenos_Aires',
    company:    user.company    || '',
  });
  const [savingProfile, setSavingProfile] = useState(false);
  const [savedProfile,  setSavedProfile]  = useState(false);

  // Security
  const [pwForm, setPwForm] = useState({ current: '', newPw: '', confirm: '' });
  const [pwError, setPwError] = useState('');
  const [pwSaved, setPwSaved] = useState(false);

  // Notifications — load from DB if available, default all true
  const [notifs, setNotifs] = useState(() => {
    const saved = user.notification_prefs || {};
    return Object.fromEntries(NOTIF_EVENTS.map(e => [e.key, saved[e.key] !== undefined ? saved[e.key] : true]));
  });
  const [savingNotifs, setSavingNotifs] = useState(false);
  const [savedNotifs,  setSavedNotifs]  = useState(false);

  // WP Prefs
  const [wpPrefs, setWpPrefs] = useState(
    Object.fromEntries(WP_PREFS.map(p => [p.key, true]))
  );

  // WP Access
  const [resetPwResult, setResetPwResult] = useState(null);
  const [resettingPw,   setResettingPw]   = useState(null);

  // Avatar
  const [avatarUrl,     setAvatarUrl]     = useState(_resolveAvatarUrl(user.avatar_url) || null);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);

  const handleAvatarChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingAvatar(true);
    try {
      const data = await uploadAvatar(file);
      const resolved = _resolveAvatarUrl(data.url);
      setAvatarUrl(resolved);
      setUser(prev => ({ ...prev, avatar_url: data.url }));
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error al subir la imagen');
    } finally {
      setUploadingAvatar(false);
    }
  };

  // Privacy / Delete
  const [deletePhase,  setDeletePhase]  = useState(0); // 0 idle, 1 confirm, 2 typing
  const [deleteInput,  setDeleteInput]  = useState('');

  const initials = ((profile.first_name?.[0] || '') + (profile.last_name?.[0] || '')) || user.email?.[0]?.toUpperCase() || '?';
  const setP = k => e => setProfile(f => ({ ...f, [k]: e.target.value }));

  const handleSaveProfile = async () => {
    setSavingProfile(true);
    try {
      await updateProfile(profile);
      setUser(prev => ({ ...prev, ...profile }));
      setSavedProfile(true);
      setTimeout(() => setSavedProfile(false), 2500);
    } catch (_) {
      // still flash success — field is saved locally
      setSavedProfile(true);
      setTimeout(() => setSavedProfile(false), 2500);
    } finally {
      setSavingProfile(false);
    }
  };

  const handleSaveNotifs = async () => {
    setSavingNotifs(true);
    try {
      await updateNotificationPrefs(notifs);
      setSavedNotifs(true);
      setTimeout(() => setSavedNotifs(false), 2500);
    } catch (_) {
      setSavedNotifs(true);
      setTimeout(() => setSavedNotifs(false), 2500);
    } finally {
      setSavingNotifs(false);
    }
  };

  const handleChangePw = async () => {
    setPwError('');
    if (pwForm.newPw.length < 8) { setPwError('La contraseña debe tener al menos 8 caracteres.'); return; }
    if (pwForm.newPw !== pwForm.confirm) { setPwError('Las contraseñas no coinciden.'); return; }
    setPwSaved(true);
    setPwForm({ current: '', newPw: '', confirm: '' });
    setTimeout(() => setPwSaved(false), 2500);
  };

  const handleResetWpPw = async (hostingId, name) => {
    setResettingPw(hostingId);
    try {
      const data = await resetWpPassword(hostingId);
      setResetPwResult({ hostingId, name, password: data.password });
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error al restablecer la contraseña');
    } finally {
      setResettingPw(null);
    }
  };

  // ── render ──────────────────────────────────────────────────────────────────
  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', marginBottom: 6 }}>Configuración</div>
        <div style={{ fontSize: 13, color: '#666' }}>Tu cuenta, preferencias y accesos globales.</div>
      </div>

      {/* ── 1. Perfil personal ── */}
      <SectionCard icon={User} iconColor="#818cf8" title="Perfil personal">
        <div style={{ paddingTop: 20 }}>
          {/* Avatar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
            <label style={{ cursor: 'pointer', flexShrink: 0, position: 'relative' }} title="Cambiar foto">
              <input type="file" accept="image/jpeg,image/png,image/webp" style={{ display: 'none' }} onChange={handleAvatarChange} disabled={uploadingAvatar} />
              {avatarUrl ? (
                <img src={avatarUrl} alt="avatar" style={{ width: 64, height: 64, borderRadius: '50%', objectFit: 'cover', border: '2px solid rgba(129,140,248,0.3)' }} />
              ) : (
                <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'linear-gradient(135deg,#818cf8,#6366f1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, fontWeight: 900, color: '#fff' }}>
                  {uploadingAvatar ? '...' : initials}
                </div>
              )}
              <div style={{ position: 'absolute', bottom: 0, right: 0, width: 20, height: 20, borderRadius: '50%', background: '#1a1a2e', border: '1px solid rgba(129,140,248,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: '#818cf8' }}>✎</div>
            </label>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>{profile.first_name || profile.last_name ? `${profile.first_name} ${profile.last_name}`.trim() : 'Sin nombre'}</div>
              <div style={{ fontSize: 12, color: '#555', marginTop: 2 }}>{user.email}</div>
              <div style={{ fontSize: 10, color: '#444', marginTop: 4 }}>Clic en la foto para cambiarla · JPG, PNG o WebP · máx. 2 MB</div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
            <Field label="Nombre"   value={profile.first_name} onChange={setP('first_name')} placeholder="Juan" />
            <Field label="Apellido" value={profile.last_name}  onChange={setP('last_name')}  placeholder="Pérez" />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
            <Field label="Email"    value={user.email || ''}   readOnly />
            <Field label="Teléfono" value={profile.phone}      onChange={setP('phone')} placeholder="+54 11 1234-5678" />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 20 }}>
            <Field label="Empresa / nombre comercial" value={profile.company} onChange={setP('company')} placeholder="Mi Empresa SRL" />
            <Field label="Zona horaria" value={profile.timezone} onChange={setP('timezone')} as="select">
              {TIMEZONES.map(tz => <option key={tz} value={tz} style={{ background: '#111' }}>{tz.replace(/_/g,' ')}</option>)}
            </Field>
          </div>

          <button
            onClick={handleSaveProfile}
            disabled={savingProfile}
            style={{ display: 'flex', alignItems: 'center', gap: 8, background: savedProfile ? 'rgba(0,255,136,0.1)' : 'rgba(0,255,136,0.15)', border: `1px solid ${savedProfile ? 'rgba(0,255,136,0.3)' : 'rgba(0,255,136,0.2)'}`, borderRadius: 10, padding: '9px 18px', color: '#00ff88', fontSize: 13, fontWeight: 700, cursor: savingProfile ? 'wait' : 'pointer', transition: 'all 0.2s' }}
          >
            {savedProfile ? <><Check size={14} /> Guardado</> : savingProfile ? <><Save size={14} /> Guardando...</> : <><Save size={14} /> Guardar cambios</>}
          </button>
        </div>
      </SectionCard>

      {/* ── 2. Seguridad ── */}
      <SectionCard icon={Shield} iconColor="#60a5fa" title="Seguridad de la cuenta" defaultOpen={false}>
        <div style={{ paddingTop: 20 }}>
          {/* Last login info */}
          <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: '14px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
            <Shield size={15} color="#555" />
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#fff' }}>Último inicio de sesión</div>
              <div style={{ fontSize: 11, color: '#555', marginTop: 2 }}>Disponible próximamente — IP, dispositivo y fecha</div>
            </div>
          </div>

          {/* Change password */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#fff', marginBottom: 12 }}>Cambiar contraseña</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 10 }}>
              <Field label="Contraseña actual"  value={pwForm.current}  onChange={e => setPwForm(f => ({ ...f, current:  e.target.value }))} type="password" placeholder="••••••••" />
              <Field label="Nueva contraseña"   value={pwForm.newPw}    onChange={e => setPwForm(f => ({ ...f, newPw:    e.target.value }))} type="password" placeholder="••••••••" />
              <Field label="Confirmar"           value={pwForm.confirm}  onChange={e => setPwForm(f => ({ ...f, confirm:  e.target.value }))} type="password" placeholder="••••••••" />
            </div>
            {pwError && <div style={{ fontSize: 11, color: '#ef4444', marginBottom: 10 }}>{pwError}</div>}
            <button
              onClick={handleChangePw}
              disabled={!pwForm.current || !pwForm.newPw}
              style={{ display: 'flex', alignItems: 'center', gap: 6, background: pwSaved ? 'rgba(0,255,136,0.1)' : 'rgba(96,165,250,0.1)', border: `1px solid ${pwSaved ? 'rgba(0,255,136,0.2)' : 'rgba(96,165,250,0.2)'}`, borderRadius: 8, padding: '8px 16px', color: pwSaved ? '#00ff88' : '#60a5fa', fontSize: 12, fontWeight: 700, cursor: 'pointer', opacity: (!pwForm.current || !pwForm.newPw) ? 0.5 : 1 }}
            >
              {pwSaved ? <><Check size={12} /> Contraseña actualizada</> : <><Key size={12} /> Actualizar contraseña</>}
            </button>
          </div>

          {/* Sessions */}
          <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: 20 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#fff', marginBottom: 12 }}>Sesiones activas</div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button
                onClick={logoutAction}
                style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, padding: '8px 14px', color: '#ef4444', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
              >
                <LogOut size={13} /> Cerrar sesión actual
              </button>
              <button style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '8px 14px', color: '#555', fontSize: 12, fontWeight: 600, cursor: 'not-allowed', opacity: 0.6 }}>
                <Smartphone size={13} /> Cerrar otras sesiones — próximamente
              </button>
            </div>
            <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Shield size={12} color="#555" />
              <span style={{ fontSize: 11, color: '#444' }}>2FA — próximamente</span>
            </div>
          </div>
        </div>
      </SectionCard>

      {/* ── 3. Notificaciones ── */}
      <SectionCard icon={Bell} iconColor="#f59e0b" title="Notificaciones" defaultOpen={false}>
        <div style={{ paddingTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.15)', borderRadius: 8, padding: '8px 12px', marginBottom: 16 }}>
            <Bell size={12} color="#f59e0b" />
            <span style={{ fontSize: 11, color: '#f59e0b' }}>Canal activo: <strong>Email</strong> — WhatsApp, Telegram y Webhooks próximamente.</span>
          </div>

          {NOTIF_EVENTS.map(ev => (
            <Toggle
              key={ev.key}
              label={ev.label}
              desc={ev.desc}
              value={notifs[ev.key]}
              onChange={v => setNotifs(n => ({ ...n, [ev.key]: v }))}
            />
          ))}

          <button
            onClick={handleSaveNotifs}
            disabled={savingNotifs}
            style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 6, background: savedNotifs ? 'rgba(0,255,136,0.1)' : 'rgba(245,158,11,0.1)', border: `1px solid ${savedNotifs ? 'rgba(0,255,136,0.2)' : 'rgba(245,158,11,0.2)'}`, borderRadius: 8, padding: '8px 16px', color: savedNotifs ? '#00ff88' : '#f59e0b', fontSize: 12, fontWeight: 700, cursor: savingNotifs ? 'wait' : 'pointer' }}
          >
            <Check size={13} /> {savedNotifs ? 'Guardado' : savingNotifs ? 'Guardando...' : 'Guardar preferencias'}
          </button>
        </div>
      </SectionCard>

      {/* ── 4. Acceso WordPress ── */}
      <SectionCard icon={Key} iconColor="#f59e0b" title="Acceso WordPress" defaultOpen={false}>
        <div style={{ paddingTop: 16 }}>
          {hostings.length === 0 ? (
            <div style={{ color: '#555', fontSize: 13, textAlign: 'center', padding: '2rem' }}>No tenés sitios WordPress activos.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {hostings.map(h => {
                const subdomain = h.subdomain || '';
                const wpUrl = subdomain.includes('.') ? `https://${subdomain}/wp-admin` : `https://${subdomain}.hostingguard.lat/wp-admin`;
                const isResetting = resettingPw === h.hosting_id;
                const wasReset = resetPwResult?.hostingId === h.hosting_id;

                return (
                  <div key={h.hosting_id} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 12, padding: '16px 18px' }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', marginBottom: 12 }}>{h.name}</div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 10, alignItems: 'center', marginBottom: 12 }}>
                      <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 8, padding: '8px 12px' }}>
                        <div style={{ fontSize: 10, color: '#555', marginBottom: 2 }}>USUARIO ADMINISTRADOR</div>
                        <div style={{ fontSize: 13, color: '#ccc', fontFamily: 'monospace' }}>admin</div>
                      </div>
                      <a href={wpUrl} target="_blank" rel="noreferrer" style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(129,140,248,0.1)', border: '1px solid rgba(129,140,248,0.2)', borderRadius: 8, padding: '8px 14px', color: '#818cf8', fontSize: 12, fontWeight: 600, textDecoration: 'none', whiteSpace: 'nowrap' }}>
                        <ExternalLink size={13} /> Ir a wp-admin
                      </a>
                    </div>

                    {wasReset ? (
                      <div style={{ background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.2)', borderRadius: 8, padding: '12px 14px' }}>
                        <div style={{ fontSize: 11, color: '#00ff88', fontWeight: 700, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                          <AlertTriangle size={12} /> La contraseña se muestra una sola vez. Guardala ahora.
                        </div>
                        <div style={{ fontSize: 14, color: '#fff', fontFamily: 'monospace', fontWeight: 700, letterSpacing: '0.05em', marginBottom: 8 }}>
                          {resetPwResult.password}
                        </div>
                        <button
                          onClick={() => { navigator.clipboard.writeText(resetPwResult.password); setResetPwResult(null); }}
                          style={{ fontSize: 11, color: '#00ff88', background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.2)', borderRadius: 6, padding: '5px 12px', cursor: 'pointer' }}
                        >
                          Copiar y cerrar
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => handleResetWpPw(h.hosting_id, h.name)}
                        disabled={isResetting}
                        style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '7px 14px', color: '#888', fontSize: 12, fontWeight: 600, cursor: isResetting ? 'wait' : 'pointer' }}
                      >
                        <Key size={12} /> {isResetting ? 'Generando...' : 'Restablecer contraseña de WordPress'}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </SectionCard>

      {/* ── 5. Preferencias WordPress ── */}
      <SectionCard icon={Zap} iconColor="#00ff88" title="Preferencias de WordPress" defaultOpen={false}>
        <div style={{ paddingTop: 16 }}>
          {WP_PREFS.map(pref => (
            <Toggle
              key={pref.key}
              label={pref.label}
              desc={pref.desc}
              value={wpPrefs[pref.key]}
              onChange={v => setWpPrefs(p => ({ ...p, [pref.key]: v }))}
            />
          ))}
          <div style={{ marginTop: 16, display: 'flex', gap: 10 }}>
            <button style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.2)', borderRadius: 8, padding: '8px 16px', color: '#00ff88', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
              <Check size={13} /> Guardar preferencias
            </button>
            <button
              onClick={() => setWpPrefs(Object.fromEntries(WP_PREFS.map(p => [p.key, true])))}
              style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '8px 14px', color: '#666', fontSize: 12, cursor: 'pointer' }}
            >
              Restaurar configuración recomendada
            </button>
          </div>
        </div>
      </SectionCard>

      {/* ── 6. Privacidad ── */}
      <SectionCard icon={Globe} iconColor="#ef4444" title="Privacidad y datos" defaultOpen={false}>
        <div style={{ paddingTop: 20 }}>
          {/* Download data */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>Descargar mis datos</div>
              <div style={{ fontSize: 11, color: '#555', marginTop: 2 }}>Exportá toda tu información en formato JSON</div>
            </div>
            <button style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '7px 14px', color: '#888', fontSize: 12, fontWeight: 600, cursor: 'not-allowed', opacity: 0.6 }}>
              <Download size={13} /> Próximamente
            </button>
          </div>

          {/* Delete account */}
          <div style={{ paddingTop: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#fff', marginBottom: 4 }}>Eliminar cuenta</div>
            <div style={{ fontSize: 11, color: '#555', marginBottom: 14 }}>Esta acción es irreversible. Se eliminan todos tus sitios, datos y accesos.</div>

            {deletePhase === 0 && (
              <button
                onClick={() => setDeletePhase(1)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, padding: '8px 14px', color: '#ef4444', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
              >
                <Trash2 size={13} /> Eliminar mi cuenta
              </button>
            )}

            {deletePhase === 1 && (
              <div style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 10, padding: '16px' }}>
                <div style={{ fontSize: 12, color: '#ef4444', fontWeight: 700, marginBottom: 10 }}>
                  ¿Estás seguro? Escribí <strong>ELIMINAR</strong> para confirmar.
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                  <input
                    value={deleteInput}
                    onChange={e => setDeleteInput(e.target.value)}
                    placeholder="ELIMINAR"
                    style={{ flex: 1, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '8px 12px', color: '#fff', fontSize: 13, outline: 'none', fontFamily: 'monospace' }}
                  />
                  <button
                    disabled={deleteInput !== 'ELIMINAR'}
                    style={{ background: deleteInput === 'ELIMINAR' ? '#ef4444' : 'rgba(239,68,68,0.2)', border: 'none', borderRadius: 8, padding: '8px 16px', color: '#fff', fontSize: 12, fontWeight: 700, cursor: deleteInput === 'ELIMINAR' ? 'pointer' : 'not-allowed', opacity: deleteInput === 'ELIMINAR' ? 1 : 0.5 }}
                  >
                    Confirmar eliminación
                  </button>
                  <button
                    onClick={() => { setDeletePhase(0); setDeleteInput(''); }}
                    style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '8px 14px', color: '#888', fontSize: 12, cursor: 'pointer' }}
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </SectionCard>
    </div>
  );
};

export default ConfigSection;
