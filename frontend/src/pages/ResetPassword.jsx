import { useState } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { ShieldCheck, Lock, Eye, EyeOff, CheckCircle2, XCircle } from 'lucide-react';
import { resetPassword } from '../services/api';

const ResetPassword = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const navigate = useNavigate();

  const [password,  setPassword]  = useState('');
  const [confirm,   setConfirm]   = useState('');
  const [showPw,    setShowPw]    = useState(false);
  const [showCf,    setShowCf]    = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState('');
  const [success,   setSuccess]   = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password.length < 8) { setError('La contraseña debe tener al menos 8 caracteres'); return; }
    if (password !== confirm)  { setError('Las contraseñas no coinciden'); return; }
    if (!token)                { setError('Enlace inválido'); return; }

    setLoading(true); setError('');
    try {
      await resetPassword(token, password);
      setSuccess(true);
      setTimeout(() => navigate('/'), 3000);
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(
        d === 'invalid_token'  ? 'El enlace es inválido o ya fue usado.'
        : d === 'token_expired'? 'El enlace expiró. Solicitá uno nuevo.'
        : 'No se pudo cambiar la contraseña. Intentá de nuevo.'
      );
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0c] flex flex-col items-center justify-center p-6">
      {/* Logo */}
      <Link to="/" className="flex items-center gap-2 mb-10">
        <div className="w-8 h-8 rounded-lg bg-green-500/10 border border-green-500/20 flex items-center justify-center">
          <ShieldCheck className="w-4 h-4 text-green-400" />
        </div>
        <span className="text-white font-black text-sm tracking-wide">HostingGuard</span>
        <span className="text-green-500 font-mono text-xs">.LAT</span>
      </Link>

      <div className="w-full max-w-sm bg-[#111] rounded-2xl border border-white/8 overflow-hidden shadow-2xl">
        <div className="h-0.5 w-full bg-gradient-to-r from-green-500/0 via-green-500 to-green-500/0" />
        <div className="p-7">
          {success ? (
            <div className="text-center py-2">
              <div className="w-14 h-14 rounded-2xl bg-green-500/10 border border-green-500/20 flex items-center justify-center mx-auto mb-4">
                <CheckCircle2 className="w-7 h-7 text-green-400" />
              </div>
              <h2 className="text-white text-lg font-black mb-2">Contraseña actualizada</h2>
              <p className="text-gray-400 text-sm leading-relaxed mb-1">
                Tu contraseña fue cambiada con éxito.
              </p>
              <p className="text-gray-500 text-xs mt-3">Redirigiendo al inicio...</p>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <h2 className="text-white text-xl font-black">Nueva contraseña</h2>
                <p className="text-gray-500 text-xs mt-0.5">Elegí una contraseña segura</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-3.5">
                {/* Password */}
                <div className="space-y-1">
                  <label className="text-[10px] font-bold uppercase tracking-wider text-gray-500">Nueva contraseña</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600 pointer-events-none" />
                    <input
                      type={showPw ? 'text' : 'password'}
                      placeholder="••••••••"
                      required
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      autoFocus
                      className="w-full py-3 pl-9 pr-10 rounded-lg bg-black/60 border border-gray-800 text-white text-sm focus:border-green-500 focus:outline-none transition-colors placeholder:text-gray-700"
                    />
                    <button type="button" onClick={() => setShowPw(v => !v)} tabIndex={-1}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400 transition-colors">
                      {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <p className="text-[10px] text-gray-600">Mínimo 8 caracteres</p>
                </div>

                {/* Confirm */}
                <div className="space-y-1">
                  <label className="text-[10px] font-bold uppercase tracking-wider text-gray-500">Confirmar contraseña</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600 pointer-events-none" />
                    <input
                      type={showCf ? 'text' : 'password'}
                      placeholder="••••••••"
                      required
                      value={confirm}
                      onChange={e => setConfirm(e.target.value)}
                      className="w-full py-3 pl-9 pr-10 rounded-lg bg-black/60 border border-gray-800 text-white text-sm focus:border-green-500 focus:outline-none transition-colors placeholder:text-gray-700"
                    />
                    <button type="button" onClick={() => setShowCf(v => !v)} tabIndex={-1}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400 transition-colors">
                      {showCf ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {error && (
                  <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-start gap-2">
                    <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                    {error}
                  </div>
                )}

                <button type="submit" disabled={loading}
                  className="w-full bg-green-500 py-3.5 rounded-xl font-black text-black text-sm hover:bg-green-400 active:scale-[.98] transition-all disabled:opacity-50 mt-1">
                  {loading ? 'Guardando...' : 'GUARDAR CONTRASEÑA'}
                </button>
              </form>

              <p className="text-center text-xs text-gray-500 mt-5 pt-4 border-t border-white/5">
                <Link to="/" className="text-green-500 font-bold hover:underline">Volver al inicio</Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ResetPassword;
