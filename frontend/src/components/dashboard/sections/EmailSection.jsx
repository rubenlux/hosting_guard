import { useState } from 'react';
import { Mail, Save, Check, Eye, EyeOff, Zap } from 'lucide-react';

const PRESETS = {
  Gmail: { host: 'smtp.gmail.com', port: '587', encryption: 'TLS', note: 'Requiere contraseña de aplicación de Google.' },
  Resend: { host: 'smtp.resend.com', port: '465', encryption: 'SSL', note: 'Usá tu API key como contraseña.' },
  Mailgun: { host: 'smtp.mailgun.org', port: '587', encryption: 'TLS', note: 'Encontrá las credenciales en tu cuenta Mailgun.' },
  Brevo: { host: 'smtp-relay.brevo.com', port: '587', encryption: 'TLS', note: 'Usá tu clave SMTP de Brevo.' },
};

const Field = ({ label, value, onChange, type = 'text', mono = false, placeholder = '' }) => (
  <div>
    <label style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: 6 }}>{label}</label>
    <input
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '9px 12px', color: '#fff', fontSize: 13, outline: 'none', fontFamily: mono ? 'monospace' : 'inherit', transition: 'border-color 0.15s' }}
      onFocus={e => e.target.style.borderColor = 'rgba(0,255,136,0.3)'}
      onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
    />
  </div>
);

const EmailSection = ({ hostings = [] }) => {
  const [form, setForm] = useState({ host: '', port: '587', encryption: 'TLS', from_name: '', from_email: '', username: '', password: '' });
  const [showPass, setShowPass] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [presetNote, setPresetNote] = useState('');
  const [selectedHosting, setSelectedHosting] = useState(hostings[0]?.hosting_id || '');

  const set = (key) => (e) => setForm(f => ({ ...f, [key]: e.target.value }));

  const applyPreset = (name) => {
    const p = PRESETS[name];
    setForm(f => ({ ...f, host: p.host, port: p.port, encryption: p.encryption }));
    setPresetNote(p.note);
  };

  const handleSave = async () => {
    setSaving(true);
    await new Promise(r => setTimeout(r, 1200));
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', marginBottom: 6 }}>Email / SMTP</div>
        <div style={{ fontSize: 13, color: '#666' }}>Configurá el servidor de email para que WordPress pueda enviar notificaciones.</div>
      </div>

      <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, padding: '24px' }}>
        {/* Hosting selector */}
        {hostings.length > 1 && (
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: 6 }}>Sitio</label>
            <select
              value={selectedHosting}
              onChange={e => setSelectedHosting(e.target.value)}
              style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '9px 12px', color: '#fff', fontSize: 13, width: '100%', outline: 'none' }}
            >
              {hostings.map(h => <option key={h.hosting_id} value={h.hosting_id} style={{ background: '#111' }}>{h.name}</option>)}
            </select>
          </div>
        )}

        {/* Presets */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>Proveedor rápido</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {Object.keys(PRESETS).map(name => (
              <button
                key={name}
                onClick={() => applyPreset(name)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '6px 14px', color: '#ccc', fontSize: 12, fontWeight: 600, cursor: 'pointer', transition: 'all 0.15s' }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(0,255,136,0.3)'; e.currentTarget.style.color = '#00ff88'; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)'; e.currentTarget.style.color = '#ccc'; }}
              >
                <Zap size={11} /> {name}
              </button>
            ))}
          </div>
          {presetNote && (
            <div style={{ marginTop: 8, fontSize: 11, color: '#f59e0b', background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.15)', borderRadius: 6, padding: '6px 10px' }}>
              {presetNote}
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px 120px', gap: 14, marginBottom: 14 }}>
          <Field label="Servidor SMTP" value={form.host} onChange={set('host')} placeholder="smtp.gmail.com" mono />
          <Field label="Puerto" value={form.port} onChange={set('port')} placeholder="587" mono />
          <div>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: 6 }}>Cifrado</label>
            <select
              value={form.encryption}
              onChange={set('encryption')}
              style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '9px 12px', color: '#fff', fontSize: 13, outline: 'none' }}
            >
              <option style={{ background: '#111' }}>TLS</option>
              <option style={{ background: '#111' }}>SSL</option>
              <option style={{ background: '#111' }}>Ninguno</option>
            </select>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
          <Field label="Nombre remitente" value={form.from_name} onChange={set('from_name')} placeholder="Mi Sitio" />
          <Field label="Email remitente" value={form.from_email} onChange={set('from_email')} placeholder="hola@misitio.com" mono />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 24 }}>
          <Field label="Usuario SMTP" value={form.username} onChange={set('username')} placeholder="usuario@gmail.com" mono />
          <div>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: 6 }}>Contraseña SMTP</label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPass ? 'text' : 'password'}
                value={form.password}
                onChange={set('password')}
                placeholder="••••••••••••"
                style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '9px 36px 9px 12px', color: '#fff', fontSize: 13, outline: 'none', fontFamily: 'monospace' }}
              />
              <button onClick={() => setShowPass(v => !v)} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#555', cursor: 'pointer', padding: 0, display: 'flex' }}>
                {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>
        </div>

        <button
          onClick={handleSave}
          disabled={saving || !form.host}
          style={{ display: 'flex', alignItems: 'center', gap: 8, background: saved ? 'rgba(0,255,136,0.1)' : 'rgba(0,255,136,0.15)', border: `1px solid ${saved ? 'rgba(0,255,136,0.3)' : 'rgba(0,255,136,0.2)'}`, borderRadius: 10, padding: '10px 20px', color: '#00ff88', fontSize: 13, fontWeight: 700, cursor: saving || !form.host ? 'not-allowed' : 'pointer', transition: 'all 0.2s', opacity: !form.host ? 0.5 : 1 }}
        >
          {saved ? <><Check size={15} /> Guardado</> : saving ? <><Save size={15} style={{ animation: 'spin 1s linear infinite' }} /> Guardando...</> : <><Save size={15} /> Guardar configuración</>}
        </button>
      </div>

      {/* Note */}
      <div style={{ marginTop: 16, padding: '12px 16px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 10 }}>
        <div style={{ fontSize: 11, color: '#555', lineHeight: 1.6 }}>
          <Mail size={11} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle', color: '#666' }} />
          La configuración se aplica al plugin WP Mail SMTP de tu instalación WordPress. Si no lo tenés instalado, podés hacerlo desde el wp-admin.
        </div>
      </div>
    </div>
  );
};

export default EmailSection;
