import React, { useState, useRef, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, Upload, FileArchive, Database, CheckCircle2,
  AlertCircle, Loader2, ExternalLink,
} from 'lucide-react';
import { uploadZip, startImport, getImportStatus } from '../services/api';

const STEPS_SQL = [
  { key: 'uploading',    label: 'Subiendo archivo' },
  { key: 'processing',   label: 'Procesando' },
  { key: 'restoring_db', label: 'Restaurando base de datos' },
  { key: 'fixing_urls',  label: 'Actualizando URLs' },
  { key: 'completed',    label: 'Completado' },
];

const stepIndex = (status) => STEPS_SQL.findIndex((s) => s.key === status);

const formatBytes = (bytes) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const ZipUploadModal = ({ isOpen, onClose, hosting }) => {
  const [mode, setMode] = useState('zip'); // 'zip' | 'sql'
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);

  // ZIP state
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [zipResult, setZipResult] = useState(null); // { success, url, error }

  // SQL state
  const [jobId, setJobId] = useState(null);
  const [sqlStatus, setSqlStatus] = useState(null); // status string
  const [sqlError, setSqlError] = useState(null);
  const [sqlDone, setSqlDone] = useState(false);

  const inputRef = useRef(null);
  const pollRef = useRef(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const reset = () => {
    stopPolling();
    setFile(null);
    setDragging(false);
    setUploading(false);
    setProgress(0);
    setZipResult(null);
    setJobId(null);
    setSqlStatus(null);
    setSqlError(null);
    setSqlDone(false);
  };

  const handleClose = () => {
    if (!uploading && !jobId) {
      reset();
      onClose();
    }
  };

  const switchMode = (m) => {
    reset();
    setMode(m);
  };

  // Poll SQL job status
  useEffect(() => {
    if (!jobId) return;
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const data = await getImportStatus(jobId);
        setSqlStatus(data.status);
        if (data.status === 'completed') {
          stopPolling();
          setSqlDone(true);
        } else if (data.status === 'failed') {
          stopPolling();
          setSqlError(data.error || 'Error durante la importación');
        }
      } catch {
        // keep polling
      }
    }, 2000);
    return () => stopPolling();
  }, [jobId]);

  const pickFile = useCallback((f) => {
    if (!f) return;
    if (mode === 'zip') {
      const validExt  = f.name.toLowerCase().endsWith('.zip');
      const validMime = f.type === 'application/zip' || f.type === 'application/x-zip-compressed';
      if (!validExt || !validMime) {
        setZipResult({ success: false, error: 'Solo se aceptan archivos .zip' });
        return;
      }
    } else {
      if (!f.name.toLowerCase().endsWith('.sql')) {
        setSqlError('Solo se aceptan archivos .sql');
        return;
      }
    }
    setZipResult(null);
    setSqlError(null);
    setFile(f);
  }, [mode]);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    pickFile(e.dataTransfer.files[0]);
  }, [pickFile]);

  const onDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);

  const handleUpload = async () => {
    if (!file || !hosting) return;

    if (mode === 'zip') {
      setUploading(true);
      setProgress(0);
      setZipResult(null);
      const tick = setInterval(() => {
        setProgress((prev) => prev < 85 ? prev + Math.random() * 12 : prev);
      }, 400);
      try {
        const data = await uploadZip(hosting.hosting_id, file);
        clearInterval(tick);
        setProgress(100);
        setZipResult({ success: true, url: data.url });
      } catch (err) {
        clearInterval(tick);
        setProgress(0);
        const detail = err?.response?.data?.detail;
        setZipResult({ success: false, error: detail ? String(detail) : 'Error al subir el archivo.' });
      } finally {
        setUploading(false);
      }
    } else {
      setUploading(true);
      setSqlError(null);
      setSqlStatus('uploading');
      try {
        const data = await startImport(hosting.hosting_id, file, null);
        setJobId(data.job_id);
        setSqlStatus('processing');
      } catch (err) {
        const detail = err?.response?.data?.detail;
        setSqlError(detail ? String(detail) : 'Error al iniciar la importación.');
        setSqlStatus(null);
      } finally {
        setUploading(false);
      }
    }
  };

  if (!isOpen) return null;

  const busy = uploading || (!!jobId && !sqlDone && !sqlError);
  const currentStep = sqlStatus ? stepIndex(sqlStatus) : -1;

  return (
    <AnimatePresence>
      {isOpen && (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(8px)' }}
          onClick={handleClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.93, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.93, y: 16 }}
            transition={{ type: 'spring', stiffness: 340, damping: 28 }}
            className="w-full max-w-md rounded-2xl shadow-2xl overflow-hidden"
            style={{ background: '#111', border: '1px solid rgba(255,255,255,0.08)' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 pt-5 pb-4"
                 style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                     style={{ background: 'rgba(0,255,136,0.1)' }}>
                  <Upload className="w-4 h-4" style={{ color: '#00ff88' }} />
                </div>
                <div>
                  <div className="text-sm font-bold text-white">Subir Sitio Web</div>
                  <div className="text-[10px] text-gray-500 font-mono">{hosting?.subdomain}</div>
                </div>
              </div>
              <button
                onClick={handleClose}
                disabled={busy}
                className="w-7 h-7 rounded-lg flex items-center justify-center transition-colors"
                style={{ background: 'rgba(255,255,255,0.05)', color: busy ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.5)' }}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* Mode tabs */}
              <div className="flex rounded-lg p-1 gap-1" style={{ background: 'rgba(255,255,255,0.05)' }}>
                {[
                  { id: 'zip', label: 'ZIP', icon: FileArchive, hint: 'Sitio estático' },
                  { id: 'sql', label: 'SQL', icon: Database, hint: 'Base de datos' },
                ].map(({ id, label, icon: Icon, hint }) => (
                  <button
                    key={id}
                    onClick={() => !busy && switchMode(id)}
                    disabled={busy}
                    className="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-xs font-semibold transition-all"
                    style={mode === id
                      ? { background: 'rgba(255,255,255,0.1)', color: 'white' }
                      : { color: busy ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.45)' }
                    }
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {label}
                    <span className="text-[9px] font-normal hidden sm:inline" style={{ color: mode === id ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.25)' }}>
                      {hint}
                    </span>
                  </button>
                ))}
              </div>

              {/* Drop zone — hidden once SQL job is running */}
              {!(jobId || sqlDone) && (
                <div
                  onDrop={onDrop}
                  onDragOver={onDragOver}
                  onDragLeave={onDragLeave}
                  onClick={() => !busy && inputRef.current?.click()}
                  className="relative rounded-xl p-7 text-center cursor-pointer transition-all"
                  style={{
                    border: `2px dashed ${dragging ? '#00ff88' : file ? 'rgba(0,255,136,0.35)' : 'rgba(255,255,255,0.12)'}`,
                    background: dragging || file ? 'rgba(0,255,136,0.04)' : 'rgba(255,255,255,0.02)',
                    cursor: busy ? 'default' : 'pointer',
                    pointerEvents: busy ? 'none' : undefined,
                  }}
                >
                  <input
                    ref={inputRef}
                    type="file"
                    accept={mode === 'zip' ? '.zip' : '.sql'}
                    className="hidden"
                    onChange={(e) => pickFile(e.target.files[0])}
                  />
                  <AnimatePresence mode="wait">
                    {file ? (
                      <motion.div key="file" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                                  className="flex flex-col items-center gap-2">
                        {mode === 'zip'
                          ? <FileArchive className="w-9 h-9" style={{ color: '#00ff88' }} />
                          : <Database className="w-9 h-9" style={{ color: '#00ff88' }} />}
                        <div className="text-sm font-semibold text-white truncate max-w-[240px]">{file.name}</div>
                        <div className="text-[11px] text-gray-500">{formatBytes(file.size)}</div>
                        {!busy && <div className="text-[10px] text-gray-600 mt-0.5">Click para cambiar</div>}
                      </motion.div>
                    ) : (
                      <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                  className="flex flex-col items-center gap-3">
                        <div className="w-12 h-12 rounded-xl flex items-center justify-center"
                             style={{ background: 'rgba(255,255,255,0.05)' }}>
                          <Upload className="w-5 h-5 text-gray-500" />
                        </div>
                        <div>
                          <div className="text-sm font-semibold text-white">
                            Arrastra tu {mode === 'zip' ? '.zip' : '.sql'} aquí
                          </div>
                          <div className="text-[11px] text-gray-500 mt-1">o haz click para seleccionar</div>
                        </div>
                        <div className="text-[10px] text-gray-600 px-3 py-1.5 rounded-full"
                             style={{ background: 'rgba(255,255,255,0.05)' }}>
                          {mode === 'zip' ? 'Archivos .zip • HTML, CSS, JS, PHP' : 'Archivos .sql • Volcado de MariaDB/MySQL'}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {/* ZIP progress */}
              {mode === 'zip' && uploading && (
                <div className="space-y-2">
                  <div className="flex justify-between text-[10px] text-gray-500 font-mono">
                    <span>Desplegando...</span>
                    <span>{Math.round(progress)}%</span>
                  </div>
                  <div className="h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.08)' }}>
                    <motion.div className="h-full rounded-full" style={{ background: '#00ff88' }}
                      animate={{ width: `${progress}%` }} transition={{ ease: 'easeOut', duration: 0.3 }} />
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-gray-500">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Extrayendo archivos...
                  </div>
                </div>
              )}

              {/* SQL pipeline stepper */}
              {mode === 'sql' && (uploading || jobId) && (
                <div className="rounded-xl p-4 space-y-3" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
                  {STEPS_SQL.filter((s) => s.key !== 'completed').map((step, i) => {
                    const done = currentStep > i || sqlDone;
                    const active = !sqlDone && currentStep === i;
                    return (
                      <div key={step.key} className="flex items-center gap-3">
                        <div className="w-5 h-5 rounded-full flex items-center justify-center shrink-0 transition-all"
                             style={{
                               background: done ? 'rgba(0,255,136,0.15)' : active ? 'rgba(0,255,136,0.08)' : 'rgba(255,255,255,0.05)',
                               border: `1px solid ${done ? 'rgba(0,255,136,0.4)' : active ? 'rgba(0,255,136,0.3)' : 'rgba(255,255,255,0.1)'}`,
                             }}>
                          {done
                            ? <CheckCircle2 className="w-3 h-3" style={{ color: '#00ff88' }} />
                            : active
                              ? <Loader2 className="w-3 h-3 animate-spin" style={{ color: '#00ff88' }} />
                              : <div className="w-1.5 h-1.5 rounded-full bg-gray-600" />}
                        </div>
                        <span className="text-xs transition-colors"
                              style={{ color: done ? '#00ff88' : active ? 'white' : 'rgba(255,255,255,0.3)' }}>
                          {step.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* ZIP result */}
              <AnimatePresence>
                {zipResult && (
                  <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                    className="rounded-xl p-4"
                    style={{
                      background: zipResult.success ? 'rgba(0,255,136,0.06)' : 'rgba(239,68,68,0.06)',
                      border: `1px solid ${zipResult.success ? 'rgba(0,255,136,0.2)' : 'rgba(239,68,68,0.2)'}`,
                    }}>
                    {zipResult.success ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: '#00ff88' }}>
                          <CheckCircle2 className="w-4 h-4" />
                          Sitio desplegado con éxito
                        </div>
                        <a href={zipResult.url} target="_blank" rel="noopener noreferrer"
                           className="flex items-center gap-1.5 font-mono text-xs hover:underline" style={{ color: '#00ff88' }}>
                          {zipResult.url}
                          <ExternalLink className="w-3 h-3 shrink-0" />
                        </a>
                      </div>
                    ) : (
                      <div className="flex items-start gap-2 text-sm text-red-400">
                        <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                        <span>{zipResult.error}</span>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* SQL done */}
              <AnimatePresence>
                {sqlDone && (
                  <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                    className="rounded-xl p-4"
                    style={{ background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.2)' }}>
                    <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: '#00ff88' }}>
                      <CheckCircle2 className="w-4 h-4" />
                      Base de datos importada correctamente
                    </div>
                  </motion.div>
                )}
                {sqlError && (
                  <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                    className="rounded-xl p-4"
                    style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}>
                    <div className="flex items-start gap-2 text-sm text-red-400">
                      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>{sqlError}</span>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Action button */}
              {!zipResult?.success && !sqlDone && !sqlError && (
                <button
                  onClick={handleUpload}
                  disabled={!file || busy}
                  className="w-full py-3 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-2"
                  style={{
                    background: file && !busy ? '#00ff88' : 'rgba(255,255,255,0.07)',
                    color: file && !busy ? '#000' : 'rgba(255,255,255,0.25)',
                    cursor: !file || busy ? 'not-allowed' : 'pointer',
                  }}
                >
                  {busy ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> {mode === 'zip' ? 'Subiendo...' : 'Importando...'}</>
                  ) : (
                    <><Upload className="w-4 h-4" /> {mode === 'zip' ? 'DESPLEGAR SITIO' : 'IMPORTAR BASE DE DATOS'}</>
                  )}
                </button>
              )}

              {(zipResult?.success || sqlDone || sqlError) && (
                <button
                  onClick={() => { if (sqlError || zipResult?.error) { reset(); } else { reset(); onClose(); } }}
                  className="w-full py-3 rounded-xl text-sm font-semibold transition-all"
                  style={{ background: 'rgba(255,255,255,0.07)', color: 'rgba(255,255,255,0.6)' }}
                >
                  {zipResult?.success || sqlDone ? 'Cerrar' : 'Intentar de nuevo'}
                </button>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default ZipUploadModal;
