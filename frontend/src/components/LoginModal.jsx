import { useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Eye, EyeOff, User, Mail, Phone, Lock } from 'lucide-react';
import { login, register } from '../services/api';
import { useAuth } from '../hooks/useAuth';

function Field({ label, icon: Icon, type = 'text', placeholder, value, onChange, required = true, hint }) {
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
          className="w-full py-3 rounded-lg bg-black/60 border border-gray-800 text-white text-sm
            focus:border-green-500 focus:outline-none transition-colors placeholder:text-gray-700
            pr-3"
          style={{ paddingLeft: Icon ? '2.25rem' : '0.75rem' }}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShow(s => !s)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400 transition-colors"
            tabIndex={-1}
          >
            {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        )}
      </div>
      {hint && <p className="text-[10px] text-gray-600">{hint}</p>}
    </div>
  );
}

const LoginModal = ({ isOpen, onClose, onLoginSuccess }) => {
  const { loginAction } = useAuth();

  const [isRegister, setIsRegister] = useState(false);

  // Login fields
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');

  // Register-only fields
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName]   = useState('');
  const [phone, setPhone]         = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState('');

  const resetForm = () => {
    setEmail(''); setPassword('');
    setFirstName(''); setLastName(''); setPhone('');
    setError('');
  };

  const switchMode = () => { resetForm(); setIsRegister(r => !r); };

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      if (isRegister) {
        if (password.length < 8) {
          setError('La contraseña debe tener al menos 8 caracteres');
          return;
        }
        await register(email, password, firstName, lastName, phone);
      }

      const data = await login(email, password);

      if (data?.status === 'ok') {
        if (data?.account_type === 'staff') {
          onClose();
          window.location.href = '/staff/dashboard';
          return;
        }
        await loginAction();
        onLoginSuccess();
        onClose();
      } else {
        throw new Error('Respuesta inesperada del servidor');
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      let msg = 'Error al conectar con el servidor';
      if (detail === 'Invalid credentials')   msg = 'Email o contraseña incorrectos';
      else if (detail === 'Email already exists') msg = 'El email ya está registrado';
      else if (typeof detail === 'string')    msg = detail;
      else if (err.response?.status === 429)  msg = 'Demasiados intentos. Esperá un momento.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-[#111] w-full max-w-md rounded-2xl relative shadow-2xl border border-white/8 overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Top accent */}
        <div className="h-0.5 w-full bg-gradient-to-r from-green-500/0 via-green-500 to-green-500/0" />

        <div className="p-7">
          {/* Header */}
          <div className="flex items-start justify-between mb-6">
            <div>
              <h2 className="text-white text-xl font-black">
                {isRegister ? 'Crear cuenta' : 'Iniciar sesión'}
              </h2>
              <p className="text-gray-500 text-xs mt-0.5">
                {isRegister ? 'Completá tus datos para comenzar' : 'Bienvenido de vuelta'}
              </p>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-500 hover:text-white">
              <X size={18} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            {/* Register-only fields */}
            {isRegister && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <Field
                    label="Nombre"
                    icon={User}
                    placeholder="Juan"
                    value={firstName}
                    onChange={e => setFirstName(e.target.value)}
                  />
                  <Field
                    label="Apellido"
                    icon={User}
                    placeholder="García"
                    value={lastName}
                    onChange={e => setLastName(e.target.value)}
                  />
                </div>
                <Field
                  label="Teléfono"
                  icon={Phone}
                  type="tel"
                  placeholder="+54 9 11 1234-5678"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  hint="Con código de país. Ej: +54 9 11 1234-5678"
                />
              </>
            )}

            <Field
              label="Email"
              icon={Mail}
              type="email"
              placeholder="tu@email.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
            />

            <Field
              label="Contraseña"
              icon={Lock}
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              hint={isRegister ? 'Mínimo 8 caracteres' : undefined}
            />

            {error && (
              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-green-500 py-3.5 rounded-xl font-black text-black text-sm
                hover:bg-green-400 active:scale-[.98] transition-all disabled:opacity-50 mt-1"
            >
              {loading
                ? 'Procesando...'
                : isRegister
                ? 'CREAR CUENTA'
                : 'ENTRAR'}
            </button>
          </form>

          <p className="text-center text-xs text-gray-500 mt-5 pt-4 border-t border-white/5">
            {isRegister ? '¿Ya tenés cuenta?' : '¿No tenés cuenta?'}{' '}
            <button onClick={switchMode} className="text-green-500 font-bold hover:underline">
              {isRegister ? 'Iniciá sesión' : 'Registrate gratis'}
            </button>
          </p>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default LoginModal;
