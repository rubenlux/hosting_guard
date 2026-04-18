import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload, CheckCircle2, XCircle, AlertTriangle,
  Terminal, Globe, Loader2, X, FileArchive, Database, ArrowRight,
} from 'lucide-react';
import { startImport, getImportStatus, getImportLogsUrl } from '../../services/api';

/* ── constants ────────────────────────────────────────────────── */
const MAX_BYTES = 500 * 1024 * 1024;

const STEPS = [
  { key: 'uploading',       label: 'Subiendo archivo'       },
  { key: 'processing',      label: 'Analizando backup'      },
  { key: 'restoring_files', label: 'Restaurando archivos'   },
  { key: 'restoring_db',    label: 'Restaurando base de datos' },
  { key: 'fixing_urls',     label: 'Reemplazando dominios'  },
  { key: 'completed',       label: 'Completado'             },
];

const STEP_INDEX = Object.fromEntries(STEPS.map((s, i) => [s.key, i]));

function detectFormat(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  if (ext === 'wpress') return 'WPRESS';
  if (ext === 'sql')    return 'SQL';
  if (ext === 'zip')    return 'ZIP';
  return null;
}

function fmtBytes(b) {
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

/* ── sub-components ──────────────────────────────────────────── */
function FormatBadge({ format }) {
  if (!format) return null;
  const cfg = {
    WPRESS: { color: 'text-blue-400',   bg: 'bg-blue-500/12 border-blue-500/25',  icon: <FileArchive className="w-3 h-3" /> },
    ZIP:    { color: 'text-amber-400',  bg: 'bg-amber-500/12 border-amber-500/25', icon: <FileArchive className="w-3 h-3" /> },
    SQL:    { color: 'text-purple-400', bg: 'bg-purple-500/12 border-purple-500/25', icon: <Database className="w-3 h-3" /> },
  }[format] || {};
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded border ${cfg.bg} ${cfg.color}`}>
      {cfg.icon}{format}
    </span>
  );
}

function StepLine({ status, currentKey }) {
  const current = STEP_INDEX[currentKey] ?? -1;
  const failed  = currentKey === 'failed';

  return (
    <div className="flex flex-col gap-0">
      {STEPS.map((s, i) => {
        const done    = !failed && current > i;
        const active  = !failed && current === i;
        const isFail  = failed && i === current;
        const pending = !done && !active && !isFail;

        const dot  = isFail  ? 'bg-red-500'
                   : done    ? 'bg-[#00ff88]'
                   : active  ? 'bg-white'
                   :           'bg-white/15';
        const text = isFail  ? 'text-red-400'
                   : done    ? 'text-white/60'
                   : active  ? 'text-white'
                   :           'text-white/25';

        return (
          <div key={s.key} className="flex items-start gap-3">
            {/* connector column */}
            <div className="flex flex-col items-center w-3 shrink-0">
              <motion.div
                className={`w-2 h-2 rounded-full mt-0.5 shrink-0 ${dot}`}
                animate={active ? { scale: [1, 1.4, 1], opacity: [1, 0.7, 1] } : {}}
                transition={{ repeat: Infinity, duration: 1.2 }}
              />
              {i < STEPS.length - 1 && (
                <div className={`w-px flex-1 min-h-[16px] mt-1 ${done ? 'bg-[#00ff88]/40' : 'bg-white/8'}`} />
              )}
            </div>
            {/* label */}
            <div className={`text-[11px] pb-4 last:pb-0 transition-colors duration-300 ${text}`}>
              {s.label}
              {active && <span className="ml-2 text-[9px] font-mono text-white/40 animate-pulse">processando...</span>}
              {done   && <span className="ml-2 text-[9px] font-mono text-[#00ff88]/50">ok</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Terminal_({ logs }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [logs]);

  return (
    <div
      ref={ref}
      className="rounded-lg bg-black/60 border border-white/6 p-3 h-44 overflow-y-auto font-mono text-[10px] leading-relaxed"
      style={{ fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}
    >
      {logs.length === 0 ? (
        <span className="text-white/20">Esperando logs...</span>
      ) : (
        logs.map((line, i) => {
          const isErr  = line.includes('✗') || line.toLowerCase().includes('error') || line.toLowerCase().includes('warn');
          const isOk   = line.includes('✓') || line.includes('ok');
          const color  = isErr ? 'text-red-400' : isOk ? 'text-[#00ff88]' : 'text-white/55';
          return (
            <div key={i} className={color}>{line}</div>
          );
        })
      )}
      <span className="inline-block w-1.5 h-3 bg-[#00ff88] opacity-70 animate-pulse align-middle ml-0.5" />
    </div>
  );
}

/* ── main component ──────────────────────────────────────────── */
export default function ImportSiteModal({ hosting, onClose, onComplete }) {
  const [step,      setStep]      = useState('upload');   // upload | running | done | failed
  const [file,      setFile]      = useState(null);
  const [dragging,  setDragging]  = useState(false);
  const [jobId,     setJobId]     = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [logs,      setLogs]      = useState([]);
  const [error,     setError]     = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const inputRef  = useRef(null);
  const pollRef   = useRef(null);
  const sseRef    = useRef(null);

  const format = file ? detectFormat(file.name) : null;

  /* ── SSE log streaming ─────────────────────────────────────── */
  const startSSE = useCallback((id) => {
    if (sseRef.current) sseRef.current.close();
    const url = getImportLogsUrl(id);
    const es = new EventSource(url, { withCredentials: true });
    es.onmessage = (e) => {
      if (e.data) setLogs(prev => [...prev, e.data]);
    };
    es.addEventListener('status', (e) => {
      if (e.data === 'completed') { es.close(); setStep('done'); }
      if (e.data === 'failed')    { es.close(); setStep('failed'); }
    });
    es.onerror = () => es.close();
    sseRef.current = es;
  }, []);

  /* ── status polling ────────────────────────────────────────── */
  useEffect(() => {
    if (!jobId || step !== 'running') return;
    pollRef.current = setInterval(async () => {
      try {
        const j = await getImportStatus(jobId);
        setJobStatus(j);
        if (j.error) setError(j.error);
        if (j.status === 'completed') { clearInterval(pollRef.current); setStep('done'); }
        if (j.status === 'failed')    { clearInterval(pollRef.current); setStep('failed'); }
      } catch { /* ignore */ }
    }, 2000);
    return () => clearInterval(pollRef.current);
  }, [jobId, step]);

  /* ── cleanup ──────────────────────────────────────────────── */
  useEffect(() => () => {
    if (sseRef.current)  sseRef.current.close();
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  /* ── drag/drop ─────────────────────────────────────────────── */
  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) validateAndSet(f);
  };
  const validateAndSet = (f) => {
    const ext = f.name.split('.').pop().toLowerCase();
    if (!['zip', 'wpress', 'sql'].includes(ext)) {
      setError('Formato no soportado. Usá .zip, .wpress o .sql');
      return;
    }
    if (f.size > MAX_BYTES) {
      setError('Archivo demasiado grande. Máximo 500 MB.');
      return;
    }
    setError(null);
    setFile(f);
  };

  /* ── submit ────────────────────────────────────────────────── */
  const handleSubmit = async () => {
    if (!file) return;
    setLoading(true);
    setUploadPct(0);
    setError(null);
    try {
      const res = await startImport(hosting.hosting_id, file, setUploadPct);
      setJobId(res.job_id);
      setJobStatus({ status: 'uploading' });
      setStep('running');
      startSSE(res.job_id);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Error al iniciar la importación';
      setError(detail);
    } finally {
      setLoading(false);
      setUploadPct(0);
    }
  };

  const handleDone = () => { onComplete?.(); onClose(); };

  /* ── render ────────────────────────────────────────────────── */
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* backdrop */}
      <motion.div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={step === 'upload' ? onClose : undefined}
      />

      <motion.div
        className="relative z-10 w-full max-w-lg bg-[#0f0f11] border border-white/8 rounded-2xl overflow-hidden shadow-2xl"
        initial={{ opacity: 0, y: 16, scale: 0.97 }}
        animate={{ opacity: 1, y: 0,  scale: 1 }}
        exit={  { opacity: 0, y: 8,   scale: 0.97 }}
        transition={{ type: 'spring', stiffness: 320, damping: 28 }}
      >
        {/* header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/6">
          <div>
            <div className="text-[13px] font-semibold text-white tracking-tight">Importar sitio</div>
            <div className="text-[10px] text-white/35 font-mono mt-0.5">{hosting.name} · {hosting.subdomain}.hostingguard.lat</div>
          </div>
          {step === 'upload' && (
            <button onClick={onClose} className="w-7 h-7 flex items-center justify-center rounded-lg bg-white/5 hover:bg-white/10 transition-colors">
              <X className="w-3.5 h-3.5 text-white/50" />
            </button>
          )}
        </div>

        {/* body */}
        <div className="p-5">
          <AnimatePresence mode="wait">

            {/* ── STEP 1: UPLOAD ─────────────────────────────── */}
            {step === 'upload' && (
              <motion.div key="upload" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                {/* drop zone */}
                <div
                  className={`relative rounded-xl border-2 border-dashed transition-all duration-200 cursor-pointer
                    ${dragging
                      ? 'border-[#00ff88]/60 bg-[#00ff88]/4'
                      : file
                      ? 'border-white/15 bg-white/3'
                      : 'border-white/10 bg-white/2 hover:border-white/20 hover:bg-white/3'
                    }`}
                  onClick={() => inputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={handleDrop}
                >
                  <input
                    ref={inputRef}
                    type="file"
                    accept=".zip,.wpress,.sql"
                    className="hidden"
                    onChange={(e) => e.target.files[0] && validateAndSet(e.target.files[0])}
                  />
                  <div className="px-6 py-8 text-center">
                    {file ? (
                      <div className="flex flex-col items-center gap-2">
                        <FileArchive className="w-8 h-8 text-white/40" />
                        <div className="text-[12px] font-medium text-white">{file.name}</div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-white/35">{fmtBytes(file.size)}</span>
                          <FormatBadge format={format} />
                        </div>
                        <button
                          className="text-[10px] text-white/25 hover:text-white/50 transition-colors mt-1"
                          onClick={(e) => { e.stopPropagation(); setFile(null); setError(null); }}
                        >
                          cambiar archivo
                        </button>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center gap-3">
                        <Upload className="w-7 h-7 text-white/25" />
                        <div>
                          <div className="text-[12px] text-white/50">Arrastrá tu backup acá</div>
                          <div className="text-[10px] text-white/25 mt-1">o hacé click para seleccionar</div>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          {['WPRESS', 'ZIP', 'SQL'].map(f => <FormatBadge key={f} format={f} />)}
                        </div>
                        <div className="text-[9px] text-white/20 font-mono">máx. 500 MB</div>
                      </div>
                    )}
                  </div>
                </div>

                {error && (
                  <div className="flex items-start gap-2 mt-3 p-3 rounded-lg bg-red-500/8 border border-red-500/20">
                    <AlertTriangle className="w-3.5 h-3.5 text-red-400 shrink-0 mt-0.5" />
                    <span className="text-[11px] text-red-300">{error}</span>
                  </div>
                )}

                {/* format info */}
                {format && (
                  <div className="mt-3 p-3 rounded-lg bg-white/3 border border-white/6 text-[10px] text-white/40">
                    {format === 'WPRESS' && 'All-in-One WP Migration — se restaurará con wp-cli + plugin'}
                    {format === 'ZIP'    && 'ZIP WordPress — se extraerá wp-content y se importará DB si existe'}
                    {format === 'SQL'    && 'SQL dump — solo base de datos'}
                  </div>
                )}

                <button
                  disabled={!file || loading}
                  onClick={handleSubmit}
                  className="w-full mt-4 py-2.5 rounded-xl text-[12px] font-semibold transition-all
                    disabled:opacity-30 disabled:cursor-not-allowed
                    bg-[#00ff88]/10 border border-[#00ff88]/20 text-[#00ff88]
                    hover:bg-[#00ff88]/15 hover:border-[#00ff88]/35
                    active:scale-[0.98]"
                >
                  {loading ? (
                    <span className="flex flex-col items-center gap-1 w-full">
                      <span className="flex items-center gap-2">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        {uploadPct < 100 ? `Subiendo... ${uploadPct}%` : 'Procesando...'}
                      </span>
                      {uploadPct > 0 && uploadPct < 100 && (
                        <span className="w-full h-0.5 rounded bg-white/10 overflow-hidden">
                          <span
                            className="block h-full bg-[#00ff88] transition-all duration-300 rounded"
                            style={{ width: `${uploadPct}%` }}
                          />
                        </span>
                      )}
                    </span>
                  ) : 'Iniciar importación'}
                </button>
              </motion.div>
            )}

            {/* ── STEP 2: RUNNING ────────────────────────────── */}
            {step === 'running' && (
              <motion.div key="running" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="flex flex-col gap-4">
                <div className="flex gap-6">
                  {/* stepper */}
                  <div className="pt-0.5 min-w-[160px]">
                    <StepLine status={jobStatus} currentKey={jobStatus?.status ?? 'uploading'} />
                  </div>
                  {/* terminal */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <Terminal className="w-3 h-3 text-white/30" />
                      <span className="text-[9px] font-mono text-white/25 uppercase tracking-widest">output</span>
                    </div>
                    <Terminal_ logs={logs} />
                  </div>
                </div>
                <div className="text-[10px] text-white/25 font-mono text-center">
                  Podés cerrar esta ventana — la importación continúa en segundo plano
                </div>
              </motion.div>
            )}

            {/* ── STEP: DONE ─────────────────────────────────── */}
            {step === 'done' && (
              <motion.div key="done" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center gap-4 py-4 text-center">
                <motion.div
                  initial={{ scale: 0 }} animate={{ scale: 1 }}
                  transition={{ type: 'spring', stiffness: 300, damping: 20, delay: 0.1 }}
                >
                  <div className="w-14 h-14 rounded-full bg-[#00ff88]/10 border border-[#00ff88]/25 flex items-center justify-center">
                    <CheckCircle2 className="w-7 h-7 text-[#00ff88]" />
                  </div>
                </motion.div>
                <div>
                  <div className="text-[14px] font-semibold text-white mb-1">Importación completada</div>
                  <div className="text-[11px] text-white/40">Sitio disponible en</div>
                </div>
                {jobStatus?.new_domain && (
                  <a
                    href={`https://${jobStatus.new_domain}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-white/10 hover:bg-white/8 transition-colors"
                  >
                    <Globe className="w-3.5 h-3.5 text-[#00ff88]" />
                    <span className="text-[12px] font-mono text-[#00ff88]">
                      https://{jobStatus.new_domain}
                    </span>
                  </a>
                )}
                {jobStatus?.original_domain && jobStatus?.new_domain && (
                  <div className="flex items-center gap-2 text-[10px] text-white/30 font-mono">
                    <span>{jobStatus.original_domain}</span>
                    <ArrowRight className="w-3 h-3" />
                    <span className="text-white/50">{jobStatus.new_domain}</span>
                  </div>
                )}
                <button
                  onClick={handleDone}
                  className="w-full py-2.5 rounded-xl text-[12px] font-semibold
                    bg-[#00ff88]/10 border border-[#00ff88]/20 text-[#00ff88]
                    hover:bg-[#00ff88]/15 hover:border-[#00ff88]/35 transition-all active:scale-[0.98]"
                >
                  Listo
                </button>
              </motion.div>
            )}

            {/* ── STEP: FAILED ───────────────────────────────── */}
            {step === 'failed' && (
              <motion.div key="failed" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="flex flex-col gap-4">
                <div className="flex items-start gap-3 p-4 rounded-xl bg-red-500/8 border border-red-500/20">
                  <XCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                  <div>
                    <div className="text-[12px] font-semibold text-red-300 mb-1">Importación fallida</div>
                    <div className="text-[11px] text-red-400/70 leading-relaxed">
                      {error || jobStatus?.error || 'Error desconocido durante la importación'}
                    </div>
                  </div>
                </div>
                {logs.length > 0 && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <Terminal className="w-3 h-3 text-white/30" />
                      <span className="text-[9px] font-mono text-white/25 uppercase tracking-widest">logs</span>
                    </div>
                    <Terminal_ logs={logs} />
                  </div>
                )}
                <button
                  onClick={onClose}
                  className="w-full py-2.5 rounded-xl text-[12px] font-semibold
                    bg-white/5 border border-white/10 text-white/60
                    hover:bg-white/8 transition-all active:scale-[0.98]"
                >
                  Cerrar
                </button>
              </motion.div>
            )}

          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}
