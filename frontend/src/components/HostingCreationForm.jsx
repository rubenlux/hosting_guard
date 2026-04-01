import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Rocket, Plus, CheckCircle2, Zap, Layout, Terminal, Globe, Database, Github } from 'lucide-react';
import { createHosting, createWordPress, deployFromGithub } from '../services/api';
import { useAuth } from '../hooks/useAuth';

const PLAN_LABELS = {
  free:     'Gratis 14d',
  personal: 'Personal $9',
  negocio:  'Negocio $19',
  agencia:  'Agencia $39',
};

const TYPES = [
  {
    id: 'static',
    label: 'Sitio Web',
    desc: 'HTML, PHP, React',
    icon: Globe,
  },
  {
    id: 'wordpress',
    label: 'WordPress',
    desc: 'One-click install',
    icon: Database,
  },
  {
    id: 'github',
    label: 'GitHub',
    desc: 'Deploy desde repo',
    icon: Github,
  },
];

const HostingCreationForm = ({ onSuccess }) => {
  const { user } = useAuth();
  const [name, setName] = useState('');
  const [plan, setPlan] = useState('free');
  const [type, setType] = useState('static');
  const [repoUrl, setRepoUrl] = useState('');
  const [branch, setBranch] = useState('main');
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

      const data = type === 'wordpress'
        ? await createWordPress(name, plan)
        : type === 'github'
        ? await deployFromGithub(name, plan, repoUrl, branch)
        : await createHosting(name, plan);

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
        <p className="text-gray-500 mb-8 text-sm">Provisionamiento automático en nuestra nube.</p>

        <form onSubmit={handleCreate} className="space-y-6">

          {/* Selector de tipo */}
          <div className="space-y-2">
            <label className="block text-[11px] font-black p-1 text-muted uppercase tracking-widest">Tipo de proyecto</label>
            <div className="grid grid-cols-3 gap-2">
              {TYPES.map((t) => {
                const Icon = t.icon;
                const active = type === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setType(t.id)}
                    className={`flex flex-col items-center gap-2 py-3 px-2 rounded-2xl border font-bold transition-all ${
                      active
                        ? 'bg-primary/10 border-primary text-primary'
                        : 'bg-background border-white/10 text-gray-500 hover:border-white/30'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    <span className="text-xs font-black">{t.label}</span>
                    <span className="text-[10px] font-normal opacity-60">{t.desc}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Campos GitHub */}
          {type === 'github' && (
            <div className="space-y-3">
              <div className="space-y-2">
                <label className="block text-[11px] font-black p-1 text-muted uppercase tracking-widest">URL del repositorio</label>
                <input
                  type="url"
                  required={type === 'github'}
                  placeholder="https://github.com/usuario/mi-proyecto"
                  className="w-full bg-background border border-white/10 rounded-2xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-sm"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <label className="block text-[11px] font-black p-1 text-muted uppercase tracking-widest">Branch</label>
                <input
                  type="text"
                  placeholder="main"
                  className="w-full bg-background border border-white/10 rounded-2xl px-5 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-sm"
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                />
              </div>
              <div className="bg-purple-500/10 border border-purple-500/20 rounded-xl px-4 py-3 text-purple-400 text-xs">
                ⚡ El sistema clona tu repo automáticamente. HTML, React y Node.js soportados.
              </div>
            </div>
          )}

          {/* Nombre del proyecto */}
          <div className="space-y-2">
            <label className="block text-[11px] font-black p-1 text-muted uppercase tracking-widest">Nombre del proyecto</label>
            <div className="relative group">
              <input
                type="text"
                required
                placeholder={type === 'wordpress' ? 'ej: mi-blog' : 'ej: mi-tienda'}
                className="w-full bg-background border border-white/10 rounded-2xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-lg group-hover:border-white/20"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <div className="absolute right-5 top-1/2 -translate-y-1/2 text-gray-600 font-mono text-xs">.hostingguard.lat</div>
            </div>
          </div>

          {/* Plan */}
          <div className="space-y-2">
            <label className="block text-[11px] font-black p-1 text-muted uppercase tracking-widest">Selecciona tu plan</label>
            <div className="grid grid-cols-3 gap-2">
              {['free', 'personal', 'negocio', 'agencia'].map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPlan(p)}
                  className={`py-3 rounded-xl border font-bold capitalize transition-all ${
                    plan === p
                      ? 'bg-primary/10 border-primary text-primary'
                      : 'bg-background border-white/10 text-gray-500 hover:border-white/30'
                  }`}
                >
                  {PLAN_LABELS[p]}
                </button>
              ))}
            </div>
          </div>

          {/* WordPress notice */}
          {type === 'wordpress' && (
            <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3 text-blue-400 text-xs">
              ⚡ WordPress + MariaDB se instalan automáticamente. Listo en 60 segundos.
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className={`w-full bg-primary text-background py-5 rounded-2xl font-black text-xl hover:scale-[1.02] transition-all shadow-xl glow-primary flex items-center justify-center gap-3 ${loading ? 'opacity-70 cursor-not-allowed' : ''}`}
          >
            {loading
              ? (type === 'wordpress' ? 'Instalando WordPress...' : type === 'github' ? 'Clonando repo...' : 'Creando...')
              : (type === 'wordpress' ? 'INSTALAR WORDPRESS' : type === 'github' ? 'DEPLOY DESDE GITHUB' : 'LANZAR PROYECTO')
            }
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
                    <CheckCircle2 className="w-6 h-6" />
                    {type === 'wordpress' ? '¡WordPress instalado!' : '¡Sitio creado con éxito!'}
                  </div>
                  <div className="bg-background/50 p-4 rounded-xl">
                    <p className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-1">Tu URL está lista:</p>
                    <a href={result.data.url} target="_blank" rel="noopener noreferrer" className="text-primary font-mono block hover:underline text-lg">
                      {result.data.url}
                    </a>
                    {type === 'wordpress' && (
                      <p className="text-gray-500 text-xs mt-2">⏳ WordPress estará listo en 30-60 segundos</p>
                    )}
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
