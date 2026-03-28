import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Rocket, Plus, CheckCircle2, Zap, Layout, Terminal } from 'lucide-react';
import { createHosting } from '../services/api';
import { useAuth } from '../hooks/useAuth';

const HostingCreationForm = ({ onSuccess }) => {
  const { user } = useAuth();
  const [name, setName] = useState('');
  const [plan, setPlan] = useState('starter');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleCreate = async (e) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);

    try {
      if (!user) {
        alert('Debes iniciar sesión primero');
        setLoading(false);
        return;
      }

      const data = await createHosting(name, plan);
      setResult({ success: true, data });
      if (onSuccess) {
          setTimeout(() => onSuccess(), 2000);
      }
    } catch (err) {
      setResult({ success: false, error: err.response?.data?.detail || err.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card p-6 md:p-10 rounded-3xl border border-white/5 relative overflow-hidden bg-surface shadow-2xl">
      <div className="absolute top-0 right-0 p-8 opacity-5">
        <Terminal className="w-32 h-32 text-primary" />
      </div>

      <div className="relative">
        <h2 className="text-2xl font-black mb-2 flex items-center gap-3">
            <Layout className="text-accent w-6 h-6" /> Nuevo Proyecto
        </h2>
        <p className="text-gray-500 mb-10 text-sm">Provisionamiento automático en nuestra nube.</p>

        <form onSubmit={handleCreate} className="space-y-6">
          <div className="space-y-2">
            <label className="block text-[11px] font-black p-1 text-muted uppercase tracking-widest">Nombre del proyecto</label>
            <div className="relative group">
              <input
                type="text"
                required
                placeholder="ej: mi-tienda"
                className="w-full bg-background border border-white/10 rounded-2xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-lg group-hover:border-white/20"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <div className="absolute right-5 top-1/2 -translate-y-1/2 text-gray-600 font-mono text-xs">.hostingguard.lat</div>
            </div>
          </div>

          <div className="space-y-2">
            <label className="block text-[11px] font-black p-1 text-muted uppercase tracking-widest">Selecciona tu plan</label>
            <div className="grid grid-cols-3 gap-2">
              {['starter', 'pro', 'business'].map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPlan(p)}
                  className={`py-3 rounded-xl border font-bold capitalize transition-all ${plan === p
                    ? 'bg-primary/10 border-primary text-primary'
                    : 'bg-background border-white/10 text-gray-500 hover:border-white/30'
                    }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className={`w-full bg-primary text-background py-5 rounded-2xl font-black text-xl hover:scale-[1.02] transition-all shadow-xl glow-primary flex items-center justify-center gap-3 ${loading ? 'opacity-70 cursor-not-allowed' : ''}`}
          >
            {loading ? 'Creando...' : 'LANZAR PROYECTO'}
            {!loading && <Plus className="w-6 h-6" />}
          </button>
        </form>

        <AnimatePresence>
          {result && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className={`mt-8 p-6 rounded-2xl border ${result.success ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30'}`}
            >
              {result.success ? (
                <div className="flex flex-col gap-4">
                  <div className="flex items-center gap-3 text-green-400 font-bold">
                    <CheckCircle2 className="w-6 h-6" /> ¡Sitio creado con éxito!
                  </div>
                  <div className="bg-background/50 p-4 rounded-xl">
                    <p className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-1">Tu URL está lista:</p>
                    <a href={result.data.url} target="_blank" rel="noopener noreferrer" className="text-primary font-mono block hover:underline text-lg">
                      {result.data.url}
                    </a>
                  </div>
                </div>
              ) : (
                <div className="text-red-400 flex items-center gap-3 font-medium text-sm">
                  <Zap className="w-6 h-6" /> Error: {result.error}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default HostingCreationForm;
