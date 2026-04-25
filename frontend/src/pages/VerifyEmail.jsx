import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ShieldCheck, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { verifyEmail } from '../services/api';

const VerifyEmail = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [status, setStatus] = useState('loading'); // 'loading' | 'success' | 'error'
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (!token) { setStatus('error'); setErrorMsg('Enlace inválido: falta el token.'); return; }
    verifyEmail(token)
      .then(() => setStatus('success'))
      .catch(err => {
        const d = err.response?.data?.detail;
        setErrorMsg(
          d === 'invalid_token' ? 'El enlace es inválido o ya fue usado.'
          : d === 'token_expired' ? 'El enlace expiró. Solicitá uno nuevo desde el login.'
          : 'No se pudo verificar el email. Intentá de nuevo.'
        );
        setStatus('error');
      });
  }, [token]);

  return (
    <div className="min-h-screen bg-[#0a0a0c] flex flex-col items-center justify-center p-6">
      {/* Logo */}
      <Link to="/" className="flex items-center gap-2 mb-10 group">
        <div className="w-8 h-8 rounded-lg bg-green-500/10 border border-green-500/20 flex items-center justify-center">
          <ShieldCheck className="w-4 h-4 text-green-400" />
        </div>
        <span className="text-white font-black text-sm tracking-wide">HostingGuard</span>
        <span className="text-green-500 font-mono text-xs">.LAT</span>
      </Link>

      <div className="w-full max-w-sm bg-[#111] rounded-2xl border border-white/8 overflow-hidden shadow-2xl">
        <div className="h-0.5 w-full bg-gradient-to-r from-green-500/0 via-green-500 to-green-500/0" />
        <div className="p-8 text-center">
          {status === 'loading' && (
            <>
              <div className="w-14 h-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mx-auto mb-4">
                <Loader2 className="w-7 h-7 text-gray-400 animate-spin" />
              </div>
              <h2 className="text-white text-lg font-black mb-2">Verificando tu email</h2>
              <p className="text-gray-500 text-sm">Un momento...</p>
            </>
          )}

          {status === 'success' && (
            <>
              <div className="w-14 h-14 rounded-2xl bg-green-500/10 border border-green-500/20 flex items-center justify-center mx-auto mb-4">
                <CheckCircle2 className="w-7 h-7 text-green-400" />
              </div>
              <h2 className="text-white text-lg font-black mb-2">Email verificado</h2>
              <p className="text-gray-400 text-sm leading-relaxed mb-6">
                Tu cuenta está activa. Ya podés crear tu primer hosting.
              </p>
              <Link to="/dashboard"
                className="block w-full py-3 rounded-xl bg-green-500 text-black text-sm font-black hover:bg-green-400 active:scale-[.98] transition-all text-center">
                Ir al panel
              </Link>
            </>
          )}

          {status === 'error' && (
            <>
              <div className="w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mx-auto mb-4">
                <XCircle className="w-7 h-7 text-red-400" />
              </div>
              <h2 className="text-white text-lg font-black mb-2">Enlace inválido</h2>
              <p className="text-gray-400 text-sm leading-relaxed mb-6">{errorMsg}</p>
              <Link to="/"
                className="block w-full py-3 rounded-xl border border-white/10 text-white text-sm font-bold hover:bg-white/5 transition-colors text-center">
                Volver al inicio
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default VerifyEmail;
