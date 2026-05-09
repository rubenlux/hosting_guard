import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Rocket, Plus, CheckCircle2, Zap, Layout, Terminal, Globe, Database, Github, ChevronDown, ChevronUp, X, Clock, AlertTriangle, Wrench, Info } from 'lucide-react';
import { createHosting, createWordPress, deployFromGithub } from '../services/api';
import { useAuth } from '../hooks/useAuth';

// ── Deploy diagnostic cards ───────────────────────────────────────────────────

function RateLimitCard({ detail, countdown }) {
  const mins = Math.ceil(countdown / 60);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 text-yellow-400 font-bold text-sm">
        <Clock className="w-5 h-5 shrink-0" />
        Límite temporal alcanzado
      </div>
      <p className="text-gray-300 text-sm">{detail}</p>
      {countdown > 0 && (
        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl px-4 py-2 text-yellow-300 font-mono text-sm text-center">
          Podés volver a intentar en {countdown >= 60 ? `${mins} min` : `${countdown}s`}
        </div>
      )}
    </div>
  );
}

function DiagnosticCard({ result }) {
  const [expanded, setExpanded] = useState(false);
  const { code, stage, detail, suggestedFix, techDetail, evidence, requestId } = result;
  const hasExtra = techDetail || evidence || requestId;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start gap-3 text-red-400 font-bold text-sm">
        <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
        Deploy no completado
      </div>

      <p className="text-gray-200 text-sm leading-relaxed">{detail}</p>

      {suggestedFix && (
        <div className="flex items-start gap-2 bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3">
          <Wrench className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
          <p className="text-blue-300 text-xs leading-relaxed">{suggestedFix}</p>
        </div>
      )}

      {hasExtra && (
        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          className="flex items-center gap-1 text-gray-500 hover:text-gray-300 text-xs transition-colors w-fit"
        >
          <Info className="w-3.5 h-3.5" />
          {expanded ? 'Ocultar detalles técnicos' : 'Ver detalles técnicos'}
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
      )}

      {expanded && hasExtra && (
        <div className="bg-black/40 border border-white/8 rounded-xl p-3 font-mono text-xs text-gray-400 space-y-1 max-h-40 overflow-y-auto">
          {code    && <div><span className="text-gray-600">code:</span>   <span className="text-red-400">{code}</span></div>}
          {stage   && <div><span className="text-gray-600">stage:</span>  <span className="text-yellow-400">{stage}</span></div>}
          {requestId && <div><span className="text-gray-600">request_id:</span> {requestId}</div>}
          {techDetail && (
            <div className="whitespace-pre-wrap break-all text-gray-500 border-t border-white/5 pt-1 mt-1">
              {techDetail}
            </div>
          )}
          {evidence && Object.keys(evidence).length > 0 && (
            <div className="whitespace-pre-wrap break-all text-gray-500 border-t border-white/5 pt-1 mt-1">
              {JSON.stringify(evidence, null, 2)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

const PLAN_LABELS = {
  free:     'Gratis',
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

const HostingCreationForm = ({ onSuccess, selectedPlan }) => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const userPlan = user?.plan || 'free';
  const isPaidUser = userPlan !== 'free';

  const [name, setName] = useState('');
  const [plan, setPlan] = useState(selectedPlan || userPlan);

  useEffect(() => {
    if (selectedPlan) setPlan(selectedPlan);
  }, [selectedPlan]);
  const [type, setType] = useState('static');
  const [repoUrl, setRepoUrl] = useState('');
  const [branch, setBranch] = useState('main');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [rootDirectory, setRootDirectory] = useState('');
  const [installCommand, setInstallCommand] = useState('');
  const [buildCommand, setBuildCommand] = useState('');
  const [startCommand, setStartCommand] = useState('');
  const [outputDirectory, setOutputDirectory] = useState('');
  const [port, setPort] = useState('');
  const [dockerfilePath, setDockerfilePath] = useState('');
  const [envVars, setEnvVars] = useState([{ key: '', value: '' }]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [retryCountdown, setRetryCountdown] = useState(0);

  useEffect(() => {
    if (retryCountdown <= 0) return;
    const t = setTimeout(() => setRetryCountdown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [retryCountdown]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);

    try {
      if (!user) {
        navigate('.', { replace: true, state: { openLogin: true } });
        setLoading(false);
        return;
      }

      const data = type === 'wordpress'
        ? await createWordPress(name, plan)
        : type === 'github'
        ? await deployFromGithub(name, plan, repoUrl, branch, {
            root_directory:   rootDirectory  || undefined,
            install_command:  installCommand || undefined,
            build_command:    buildCommand   || undefined,
            start_command:    startCommand   || undefined,
            output_directory: outputDirectory|| undefined,
            port:             port ? parseInt(port, 10) : undefined,
            dockerfile_path:  dockerfilePath || undefined,
            env_vars: Object.fromEntries(
              envVars.filter(e => e.key.trim()).map(e => [e.key.trim(), e.value])
            ),
          })
        : await createHosting(name, plan);

      setResult({ success: true, data });
      if (onSuccess) {
        setTimeout(() => onSuccess(), 2000);
      }
    } catch (err) {
      const status       = err.response?.status;
      const data         = err.response?.data || {};
      const detail       = data.detail || '';
      const code         = data.code   || '';
      const stage        = data.stage  || '';
      const suggestedFix = data.suggested_fix || '';
      const techDetail   = data.technical_detail || '';
      const evidence     = data.evidence || null;
      const retryAfter   = data.retry_after_seconds || 0;
      const requestId    = data.request_id || '';

      if (status === 429 || code === 'deploy_rate_limit_exceeded') {
        if (retryAfter > 0) setRetryCountdown(retryAfter);
        setResult({
          success: false,
          isRateLimit: true,
          detail: detail || 'Alcanzaste el límite de deploys por hora. Esperá unos minutos antes de volver a intentar.',
          retryAfter,
        });
      } else if (code && stage) {
        // Structured deploy diagnostic error
        setResult({ success: false, isDiagnostic: true, code, stage, detail, suggestedFix, techDetail, evidence, requestId });
      } else {
        // Fallback: legacy / validation errors
        let errorMsg = 'Error al crear el proyecto. Inténtalo de nuevo.';
        if (detail.includes('ya existe') || detail.includes('already exists')) {
          errorMsg = 'Ya existe un proyecto con ese nombre.';
        } else if (detail.includes('plan') || detail.includes('suscripción')) {
          errorMsg = 'Tu plan actual no permite esta acción. Actualiza tu suscripción.';
        } else if (detail.includes('IP') || detail.includes('free')) {
          errorMsg = 'Solo se permite un alojamiento gratuito por dirección IP.';
        } else if (detail.includes('nombre') || detail.includes('inválido')) {
          errorMsg = 'Nombre de proyecto inválido. Usa solo letras, números y guiones.';
        } else if (detail && (status === 422 || status === 400)) {
          errorMsg = detail;
        }
        setResult({ success: false, error: errorMsg });
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div id="nuevo-proyecto" className="glass-card p-6 md:p-10 rounded-3xl border border-white/5 relative overflow-hidden bg-surface shadow-2xl">
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
              {/* Advanced config toggle */}
              <button
                type="button"
                onClick={() => setShowAdvanced(v => !v)}
                className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors py-1"
              >
                {showAdvanced ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                Configuración avanzada
              </button>

              {showAdvanced && (
                <div className="space-y-3 border border-white/6 rounded-xl px-4 py-4 bg-white/[0.02]">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <label className="block text-[10px] font-bold text-gray-600 uppercase tracking-widest">Directorio raíz</label>
                      <input type="text" placeholder="ej: frontend" value={rootDirectory} onChange={e => setRootDirectory(e.target.value)}
                        className="w-full bg-background border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-primary/50 font-mono" />
                    </div>
                    <div className="space-y-1">
                      <label className="block text-[10px] font-bold text-gray-600 uppercase tracking-widest">Puerto</label>
                      <input type="number" placeholder="80" value={port} onChange={e => setPort(e.target.value)}
                        className="w-full bg-background border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-primary/50 font-mono" />
                    </div>
                  </div>
                  <div className="space-y-1">
                    <label className="block text-[10px] font-bold text-gray-600 uppercase tracking-widest">Comando de instalación</label>
                    <input type="text" placeholder="npm install" value={installCommand} onChange={e => setInstallCommand(e.target.value)}
                      className="w-full bg-background border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-primary/50 font-mono" />
                  </div>
                  <div className="space-y-1">
                    <label className="block text-[10px] font-bold text-gray-600 uppercase tracking-widest">Comando de build</label>
                    <input type="text" placeholder="npm run build" value={buildCommand} onChange={e => setBuildCommand(e.target.value)}
                      className="w-full bg-background border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-primary/50 font-mono" />
                  </div>
                  <div className="space-y-1">
                    <label className="block text-[10px] font-bold text-gray-600 uppercase tracking-widest">Comando de inicio (app server)</label>
                    <input type="text" placeholder="uvicorn app.main:app --host 0.0.0.0 --port 8000" value={startCommand} onChange={e => setStartCommand(e.target.value)}
                      className="w-full bg-background border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-primary/50 font-mono" />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <label className="block text-[10px] font-bold text-gray-600 uppercase tracking-widest">Directorio de salida</label>
                      <input type="text" placeholder="dist" value={outputDirectory} onChange={e => setOutputDirectory(e.target.value)}
                        className="w-full bg-background border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-primary/50 font-mono" />
                    </div>
                    <div className="space-y-1">
                      <label className="block text-[10px] font-bold text-gray-600 uppercase tracking-widest">Ruta Dockerfile</label>
                      <input type="text" placeholder="Dockerfile" value={dockerfilePath} onChange={e => setDockerfilePath(e.target.value)}
                        className="w-full bg-background border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-primary/50 font-mono" />
                    </div>
                  </div>

                  {/* Env vars */}
                  <div className="space-y-2">
                    <label className="block text-[10px] font-bold text-gray-600 uppercase tracking-widest">Variables de entorno</label>
                    {envVars.map((ev, i) => (
                      <div key={i} className="flex gap-2">
                        <input type="text" placeholder="KEY" value={ev.key} onChange={e => setEnvVars(v => v.map((x, j) => j === i ? { ...x, key: e.target.value } : x))}
                          className="w-2/5 bg-background border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-primary/50 font-mono" />
                        <input type="text" placeholder="value" value={ev.value} onChange={e => setEnvVars(v => v.map((x, j) => j === i ? { ...x, value: e.target.value } : x))}
                          className="flex-1 bg-background border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-primary/50 font-mono" />
                        {envVars.length > 1 && (
                          <button type="button" onClick={() => setEnvVars(v => v.filter((_, j) => j !== i))} className="text-gray-600 hover:text-red-400 transition-colors">
                            <X size={13} />
                          </button>
                        )}
                      </div>
                    ))}
                    <button type="button" onClick={() => setEnvVars(v => [...v, { key: '', value: '' }])}
                      className="text-xs text-gray-600 hover:text-gray-400 transition-colors flex items-center gap-1">
                      <Plus size={11} /> Agregar variable
                    </button>
                  </div>
                </div>
              )}

              <div className="bg-purple-500/10 border border-purple-500/20 rounded-xl px-4 py-3 text-purple-400 text-xs">
                El sistema clona tu repo automáticamente. HTML, React, Node.js y Python soportados.
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
            <label className="block text-[11px] font-black p-1 text-muted uppercase tracking-widest">Plan</label>
            {isPaidUser ? (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-primary/30 bg-primary/5">
                <span className="text-primary font-black text-sm">{PLAN_LABELS[userPlan]}</span>
                <span className="text-gray-500 text-xs">— tu plan activo</span>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
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
            )}
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
              ) : result.isRateLimit ? (
                <RateLimitCard detail={result.detail} countdown={retryCountdown} />
              ) : result.isDiagnostic ? (
                <DiagnosticCard result={result} />
              ) : (
                <div className="text-red-400 flex items-center gap-3 font-medium text-sm">
                  <Zap className="w-6 h-6" /> {result.error}
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
