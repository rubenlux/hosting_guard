import { useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Eye, EyeOff, User, Mail, Phone, Lock, ArrowLeft, CheckCircle2, Send } from 'lucide-react';
import { login, register, forgotPassword, resendVerification } from '../services/api';
import { useAuth } from '../hooks/useAuth';

// ── Shared input field ────────────────────────────────────────────────────────
function Field({ label, icon: Icon, type = 'text', placeholder, value, onChange, required = true, hint, autoFocus }) {
  const [show, setShow] = useState(false);
  const isPassword = type === 'password';
  return (
    <div className="space-y-1">
      <label className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{label}</label>
      <div className="relative">
        {Icon && <Icon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600 pointer-events-none" />}
        <input
          type={isPassword ? (show ? 'text' : 'password') : type}
          placeholder={placeholder}
          required={required}
          value={value}
          onChange={onChange}
          autoFocus={autoFocus}
          className="w-full py-3 rounded-lg bg-black/60 border border-gray-800 text-white text-sm
            focus:border-green-500 focus:outline-none transition-colors placeholder:text-gray-700"
          style={{ paddingLeft: Icon ? '2.25rem' : '0.75rem', paddingRight: isPassword ? '2.5rem' : '0.75rem' }}
        />
        {isPassword && (
          <button type="button" onClick={() => setShow(s => !s)} tabIndex={-1}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400 transition-colors">
            {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        )}
      </div>
      {hint && <p className="text-[10px] text-gray-600">{hint}</p>}
    </div>
  );
}

// ── Modes: 'login' | 'register' | 'forgot' | 'forgot_sent' | 'registered'
const LoginModal = ({ isOpen, onClose, onLoginSuccess }) => {
  const { loginAction } = useAuth();

  const [mode, setMode]           = useState('login');
  const [email, setEmail]         = useState('');
  const [password, setPassword]   = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName]   = useState('');
  const [phone, setPhone]         = useState('');
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');
  const [resending, setResending] = useState(false);

  const reset = () => {
    setEmail(''); setPassword('');
    setFirstName(''); setLastName(''); setPhone('');
    setError('');
  };

  const go = (m) => { reset(); setMode(m); };

  if (!isOpen) return null;

  // ── Submit handlers ─────────────────────────────────────────────────────────
  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      const data = await login(email, password);
      if (data?.status === 'ok') {
        if (data?.account_type === 'staff') { onClose(); window.location.href = '/staff/dashboard'; return; }
        await loginAction();
        onLoginSuccess();
        onClose();
      } else { throw new Error('Respuesta inesperada'); }
    } catch (err) {
      const d = err.response?.data?.detail;
      if (d === 'Invalid credentials')   setError('Email o contraseña incorrectos');
      else if (err.response?.status === 429) setError('Demasiados intentos. Esperá un momento.');
      else setError(d || 'Error al conectar con el servidor');
    } finally { setLoading(false); }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    if (password.length < 8) { setError('La contraseña debe tener al menos 8 caracteres'); return; }
    setLoading(true); setError('');
    try {
      await register(email, password, firstName, lastName, phone);
      setMode('registered');
    } catch (err) {
      const d = err.response?.data?.detail;
      if (d === 'Email already exists') setError('El email ya está registrado');
      else setError(d || 'Error al crear la cuenta');
    } finally { setLoading(false); }
  };

  const handleForgot = async (e) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      await forgotPassword(email);
      setMode('forgot_sent');
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(d || 'Error al procesar la solicitud');
    } finally { setLoading(false); }
  };

  const handleResend = async () => {
    setResending(true);
    try { await resendVerification(email); }
    catch (_) {} // silent — same message regardless
    finally { setResending(false); }
  };

  // ── Shell ───────────────────────────────────────────────────────────────────
  return createPortal(
    <div className="fixed inset-0 z-[9999] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}>
      <div className="bg-[#111] w-full max-w-md rounded-2xl relative shadow-2xl border border-white/8 overflow-hidden"
        onClick={e => e.stopPropagation()}>

        {/* top accent */}
        <div className="h-0.5 w-full bg-gradient-to-r from-green-500/0 via-green-500 to-green-500/0" />

        <div className="p-7">
          {/* ── LOGIN ── */}
          {mode === 'login' && (
            <>
              <Header title="Iniciar sesión" sub="Bienvenido de vuelta" onClose={onClose} />
              <form onSubmit={handleLogin} className="space-y-3.5">
                <Field label="Email" icon={Mail} type="email" placeholder="tu@email.com" value={email} onChange={e => setEmail(e.target.value)} autoFocus />
                <Field label="Contraseña" icon={Lock} type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} />
                <button type="button" onClick={() => go('forgot')}
                  className="text-xs text-gray-500 hover:text-green-400 transition-colors">
                  ¿Olvidaste tu contraseña?
                </button>
                <ErrorBox msg={error} />
                <SubmitBtn loading={loading} label="ENTRAR" />
              </form>
              <Toggle q="¿No tenés cuenta?" link="Registrate gratis" onClick={() => go('register')} />
            </>
          )}

          {/* ── REGISTER ── */}
          {mode === 'register' && (
            <>
              <Header title="Crear cuenta" sub="Completá tus datos para comenzar" onClose={onClose} />
              <form onSubmit={handleRegister} className="space-y-3.5">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Nombre"   icon={User} placeholder="Juan"   value={firstName} onChange={e => setFirstName(e.target.value)} />
                  <Field label="Apellido" icon={User} placeholder="García" value={lastName}  onChange={e => setLastName(e.target.value)} />
                </div>
                <Field label="Teléfono" icon={Phone} type="tel" placeholder="+54 9 11 1234-5678"
                  value={phone} onChange={e => setPhone(e.target.value)}
                  hint="Con código de país. Ej: +54 9 11 1234-5678" />
                <Field label="Email" icon={Mail} type="email" placeholder="tu@email.com" value={email} onChange={e => setEmail(e.target.value)} />
                <Field label="Contraseña" icon={Lock} type="password" placeholder="••••••••"
                  value={password} onChange={e => setPassword(e.target.value)}
                  hint="Mínimo 8 caracteres" />
                <ErrorBox msg={error} />
                <SubmitBtn loading={loading} label="CREAR CUENTA" />
              </form>
              <Toggle q="¿Ya tenés cuenta?" link="Iniciá sesión" onClick={() => go('login')} />
            </>
          )}

          {/* ── POST-REGISTER: check email ── */}
          {mode === 'registered' && (
            <div className="text-center py-2">
              <button onClick={onClose} className="absolute top-5 right-5 p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-500">
                <X size={18} />
              </button>
              <div className="w-14 h-14 rounded-2xl bg-green-500/10 border border-green-500/20 flex items-center justify-center mx-auto mb-4">
                <Mail className="w-7 h-7 text-green-400" />
              </div>
              <h2 className="text-white text-lg font-black mb-2">Revisá tu email</h2>
              <p className="text-gray-400 text-sm leading-relaxed mb-1">
                Enviamos un enlace de verificación a:
              </p>
              <p className="text-green-400 font-semibold text-sm mb-5">{email}</p>
              <p className="text-gray-500 text-xs leading-relaxed mb-6">
                Hacé clic en el enlace del email para activar tu cuenta. El enlace expira en 24 horas.
              </p>
              <button onClick={handleResend} disabled={resending}
                className="text-xs text-gray-500 hover:text-green-400 transition-colors disabled:opacity-50 flex items-center gap-1.5 mx-auto">
                {resending ? <><Send className="w-3 h-3 animate-pulse" /> Enviando...</> : <><Send className="w-3 h-3" /> Reenviar email de verificación</>}
              </button>
              <button onClick={() => go('login')}
                className="mt-4 w-full py-3 rounded-xl border border-white/10 text-white text-sm font-bold hover:bg-white/5 transition-colors">
                Ir a iniciar sesión
              </button>
            </div>
          )}

          {/* ── FORGOT PASSWORD ── */}
          {mode === 'forgot' && (
            <>
              <div className="flex items-center gap-3 mb-6">
                <button onClick={() => go('login')} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-500 hover:text-white">
                  <ArrowLeft size={16} />
                </button>
                <div>
                  <h2 className="text-white text-xl font-black">Recuperar contraseña</h2>
                  <p className="text-gray-500 text-xs mt-0.5">Te enviamos un enlace a tu email</p>
                </div>
                <button onClick={onClose} className="ml-auto p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-500">
                  <X size={18} />
                </button>
              </div>
              <form onSubmit={handleForgot} className="space-y-3.5">
                <Field label="Email" icon={Mail} type="email" placeholder="tu@email.com"
                  value={email} onChange={e => setEmail(e.target.value)} autoFocus />
                <ErrorBox msg={error} />
                <SubmitBtn loading={loading} label="ENVIAR ENLACE" />
              </form>
            </>
          )}

          {/* ── FORGOT SENT ── */}
          {mode === 'forgot_sent' && (
            <div className="text-center py-2">
              <button onClick={onClose} className="absolute top-5 right-5 p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-500">
                <X size={18} />
              </button>
              <div className="w-14 h-14 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto mb-4">
                <CheckCircle2 className="w-7 h-7 text-blue-400" />
              </div>
              <h2 className="text-white text-lg font-black mb-2">Revisá tu email</h2>
              <p className="text-gray-400 text-sm leading-relaxed mb-1">
                Si existe una cuenta con:
              </p>
              <p className="text-blue-400 font-semibold text-sm mb-5">{email}</p>
              <p className="text-gray-500 text-xs leading-relaxed mb-6">
                recibirás un enlace para restablecer tu contraseña. Válido por 1 hora.
              </p>
              <button onClick={() => go('login')}
                className="w-full py-3 rounded-xl border border-white/10 text-white text-sm font-bold hover:bg-white/5 transition-colors">
                Volver a iniciar sesión
              </button>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
};

// ── Small helpers ─────────────────────────────────────────────────────────────
function Header({ title, sub, onClose }) {
  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <h2 className="text-white text-xl font-black">{title}</h2>
        <p className="text-gray-500 text-xs mt-0.5">{sub}</p>
      </div>
      <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-500 hover:text-white">
        <X size={18} />
      </button>
    </div>
  );
}

function ErrorBox({ msg }) {
  if (!msg) return null;
  return <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">{msg}</div>;
}

function SubmitBtn({ loading, label }) {
  return (
    <button type="submit" disabled={loading}
      className="w-full bg-green-500 py-3.5 rounded-xl font-black text-black text-sm hover:bg-green-400 active:scale-[.98] transition-all disabled:opacity-50 mt-1">
      {loading ? 'Procesando...' : label}
    </button>
  );
}

function Toggle({ q, link, onClick }) {
  return (
    <p className="text-center text-xs text-gray-500 mt-5 pt-4 border-t border-white/5">
      {q}{' '}
      <button onClick={onClick} className="text-green-500 font-bold hover:underline">{link}</button>
    </p>
  );
}

export default LoginModal;
