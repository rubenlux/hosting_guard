import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { login, register } from '../services/api';
import { useAuth } from '../hooks/useAuth';

const LoginModal = ({ isOpen, onClose, onLoginSuccess }) => {
  const { loginAction } = useAuth();

  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      if (isRegister) {
        await register(email, password);
      }

      const data = await login(email, password);
      loginAction(data.access_token);

      onLoginSuccess();
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al conectar con el servidor');
    } finally {
      setLoading(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-[9999] bg-black/60 flex items-center justify-center p-4">
      <div className="bg-[#111] w-full max-w-md p-6 rounded-xl relative shadow-2xl border border-white/5">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-white transition-colors"
        >
          <X size={20} />
        </button>

        <h2 className="text-white text-xl font-bold mb-6">
          {isRegister ? 'Crear cuenta' : 'Iniciar sesión'}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-xs text-gray-500 font-bold uppercase">Email</label>
            <input
              type="email"
              placeholder="tu@email.com"
              required
              className="w-full p-3 rounded bg-black border border-gray-800 text-white focus:border-green-500 focus:outline-none transition-colors"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs text-gray-500 font-bold uppercase">Contraseña</label>
            <input
              type="password"
              placeholder="••••••••"
              required
              className="w-full p-3 rounded bg-black border border-gray-800 text-white focus:border-green-500 focus:outline-none transition-colors"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {error && (
            <p className="text-red-500 text-sm italic">{error}</p>
          )}

          <button
            disabled={loading}
            className="w-full bg-green-500 py-3.5 rounded font-black text-black hover:bg-green-400 transition-colors disabled:opacity-50 mt-2"
          >
            {loading
              ? 'Procesando...'
              : isRegister
              ? 'REGISTRARSE'
              : 'ENTRAR'}
          </button>
        </form>

        <p className="text-center text-sm text-gray-400 mt-6 pt-4 border-t border-white/5">
          {isRegister ? '¿Ya tenés cuenta?' : '¿No tenés cuenta?'}{' '}
          <button
            onClick={() => setIsRegister(!isRegister)}
            className="text-green-500 font-bold hover:underline"
          >
            {isRegister ? 'Inicia sesión' : 'Registrate gratis'}
          </button>
        </p>
      </div>
    </div>,
    document.body
  );
};

export default LoginModal;
