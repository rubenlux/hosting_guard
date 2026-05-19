import { Link } from 'react-router-dom';
import { ShieldCheck, ArrowLeft } from 'lucide-react';

export default function NotFound() {
  return (
    <div className="min-h-screen bg-[#080809] flex flex-col items-center justify-center text-white px-6">
      <ShieldCheck className="w-10 h-10 text-[#00ff88]/40 mb-6" />
      <p className="text-6xl font-black text-white/10 mb-2">404</p>
      <h1 className="text-xl font-bold mb-2">Página no encontrada</h1>
      <p className="text-sm text-white/40 mb-8 text-center max-w-sm">
        La dirección que buscás no existe o fue movida.
      </p>
      <Link
        to="/"
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-white/70 hover:text-white hover:bg-white/10 transition"
      >
        <ArrowLeft size={15} />
        Volver al inicio
      </Link>
    </div>
  );
}
