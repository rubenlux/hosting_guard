import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, RefreshCw } from 'lucide-react';
import { staffLogin } from '../services/api';

export default function StaffLogin() {
  const navigate = useNavigate();
  const [form, setForm]     = useState({ email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await staffLogin(form.email, form.password);
      navigate('/staff/dashboard');
    } catch (err) {
      setError(err?.response?.data?.detail || 'Credenciales incorrectas');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <div className="w-12 h-12 rounded-2xl bg-amber-500/15 flex items-center justify-center mx-auto mb-4">
            <Shield className="w-6 h-6 text-amber-400" />
          </div>
          <h1 className="text-lg font-bold text-white">Panel de colaboradores</h1>
          <p className="text-[11px] text-gray-500 mt-1">Hosting Guard — Acceso staff</p>
        </div>

        <form onSubmit={submit} className="bg-[#111] border border-white/5 rounded-2xl p-6 space-y-4">
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 text-[11px] text-red-400">
              {error}
            </div>
          )}

          <div>
            <label className="block text-[10px] uppercase tracking-wider text-gray-500 mb-1.5">
              Email
            </label>
            <input
              type="email" required autoFocus
              value={form.email}
              onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-[13px] text-white placeholder-gray-700 outline-none focus:border-amber-500/50 transition-colors"
              placeholder="tu@email.com"
            />
          </div>

          <div>
            <label className="block text-[10px] uppercase tracking-wider text-gray-500 mb-1.5">
              Contraseña
            </label>
            <input
              type="password" required
              value={form.password}
              onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-[13px] text-white placeholder-gray-700 outline-none focus:border-amber-500/50 transition-colors"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit" disabled={loading}
            className="w-full py-2.5 rounded-xl text-[12px] font-bold bg-amber-500/15 text-amber-400
              hover:bg-amber-500/25 transition-colors disabled:opacity-50 disabled:cursor-not-allowed
              flex items-center justify-center gap-2"
          >
            {loading
              ? <><RefreshCw className="w-4 h-4 animate-spin" /> Verificando...</>
              : 'Iniciar sesión'}
          </button>
        </form>

        <p className="text-center text-[10px] text-gray-700">
          ¿Eres cliente?{' '}
          <a href="/" className="text-gray-500 hover:text-white underline">Ir al inicio</a>
        </p>
      </div>
    </div>
  );
}
