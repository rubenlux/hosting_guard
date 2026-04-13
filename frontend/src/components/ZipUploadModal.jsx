import React, { useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Upload, FileArchive, CheckCircle2, AlertCircle, Loader, ExternalLink } from 'lucide-react';
import { uploadZip } from '../services/api';

const ZipUploadModal = ({ isOpen, onClose, hosting }) => {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null); // { success, url, error }
  const inputRef = useRef(null);

  const reset = () => {
    setFile(null);
    setDragging(false);
    setUploading(false);
    setProgress(0);
    setResult(null);
  };

  const handleClose = () => {
    if (!uploading) {
      reset();
      onClose();
    }
  };

  const pickFile = (f) => {
    if (!f) return;
    // Validar tanto por extensión como por MIME type para dificultar bypass
    const validMime = f.type === 'application/zip' || f.type === 'application/x-zip-compressed';
    const validExt  = f.name.toLowerCase().endsWith('.zip');
    if (!validExt || !validMime) {
      setResult({ success: false, error: 'Solo se aceptan archivos .zip' });
      return;
    }
    setResult(null);
    setFile(f);
  };

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    pickFile(e.dataTransfer.files[0]);
  }, []);

  const onDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);

  const handleUpload = async () => {
    if (!file || !hosting) return;
    setUploading(true);
    setProgress(0);
    setResult(null);

    // Simulate progress while request is in-flight
    const tick = setInterval(() => {
      setProgress(prev => prev < 85 ? prev + Math.random() * 12 : prev);
    }, 400);

    try {
      const data = await uploadZip(hosting.hosting_id, file);
      clearInterval(tick);
      setProgress(100);
      setResult({ success: true, url: data.url });
    } catch (err) {
      clearInterval(tick);
      setProgress(0);
      // No exponer detail interno del servidor al usuario
      setResult({ success: false, error: 'Error al subir el archivo. Inténtalo de nuevo.' });
    } finally {
      setUploading(false);
    }
  };

  const formatBytes = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(6px)' }}
          onClick={handleClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.93, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.93, y: 16 }}
            transition={{ type: 'spring', stiffness: 340, damping: 28 }}
            className="w-full max-w-md bg-white border border-gray-100 rounded-3xl shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 pt-6 pb-4 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-[#00ff88]/10 flex items-center justify-center">
                  <Upload className="w-4 h-4 text-[#00ff88]" />
                </div>
                <div>
                  <div className="text-sm font-black text-gray-900">Subir Sitio Web</div>
                  <div className="text-[10px] text-gray-500 font-mono truncate max-w-[200px]">
                    {hosting?.subdomain}
                  </div>
                </div>
              </div>
              <button
                onClick={handleClose}
                disabled={uploading}
                className="w-8 h-8 rounded-lg bg-gray-50 text-gray-500 hover:text-gray-700 hover:bg-gray-100 flex items-center justify-center transition-all"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              {/* Drop zone */}
              {!result?.success && (
                <div
                  onDrop={onDrop}
                  onDragOver={onDragOver}
                  onDragLeave={onDragLeave}
                  onClick={() => !uploading && inputRef.current?.click()}
                  className={`
                    relative border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all
                    ${dragging
                      ? 'border-[#00ff88] bg-[#00ff88]/5'
                      : file
                        ? 'border-[#00ff88]/40 bg-[#00ff88]/5'
                        : 'border-gray-200 bg-gray-50 hover:border-indigo-200 hover:bg-indigo-50'
                    }
                    ${uploading ? 'pointer-events-none' : ''}
                  `}
                >
                  <input
                    ref={inputRef}
                    type="file"
                    accept=".zip"
                    className="hidden"
                    onChange={(e) => pickFile(e.target.files[0])}
                  />

                  <AnimatePresence mode="wait">
                    {file ? (
                      <motion.div
                        key="file"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="flex flex-col items-center gap-2"
                      >
                        <FileArchive className="w-10 h-10 text-[#00ff88]" />
                        <div className="text-sm font-bold text-gray-900 truncate max-w-[260px]">{file.name}</div>
                        <div className="text-[11px] text-gray-500">{formatBytes(file.size)}</div>
                        {!uploading && (
                          <div className="text-[10px] text-gray-600 mt-1">Click para cambiar</div>
                        )}
                      </motion.div>
                    ) : (
                      <motion.div
                        key="empty"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="flex flex-col items-center gap-3"
                      >
                        <div className="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center">
                          <Upload className="w-6 h-6 text-gray-500" />
                        </div>
                        <div>
                          <div className="text-sm font-bold text-gray-900">Arrastra tu .zip aquí</div>
                          <div className="text-[11px] text-gray-500 mt-1">o haz click para seleccionar</div>
                        </div>
                        <div className="text-[10px] text-gray-600 bg-gray-100 px-3 py-1.5 rounded-full">
                          Solo archivos .zip • Máx. 50MB
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {/* Progress bar */}
              {uploading && (
                <div className="space-y-2">
                  <div className="flex justify-between text-[10px] text-gray-500 font-mono">
                    <span>Desplegando...</span>
                    <span>{Math.round(progress)}%</span>
                  </div>
                  <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-[#00ff88] rounded-full"
                      animate={{ width: `${progress}%` }}
                      transition={{ ease: 'easeOut', duration: 0.3 }}
                    />
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-gray-500">
                    <Loader className="w-3 h-3 animate-spin" />
                    Extrayendo y copiando archivos al servidor...
                  </div>
                </div>
              )}

              {/* Result */}
              <AnimatePresence>
                {result && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`rounded-2xl p-4 border ${
                      result.success
                        ? 'bg-[#00ff88]/10 border-[#00ff88]/30'
                        : 'bg-red-500/10 border-red-500/30'
                    }`}
                  >
                    {result.success ? (
                      <div className="space-y-3">
                        <div className="flex items-center gap-2 text-[#00ff88] font-bold text-sm">
                          <CheckCircle2 className="w-5 h-5" />
                          ¡Sitio desplegado con éxito!
                        </div>
                        <a
                          href={result.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-2 text-[#00ff88] font-mono text-sm hover:underline"
                        >
                          {result.url}
                          <ExternalLink className="w-3.5 h-3.5 shrink-0" />
                        </a>
                        <p className="text-[10px] text-gray-500">
                          Tu sitio está activo en segundos. SSL ya está configurado.
                        </p>
                      </div>
                    ) : (
                      <div className="flex items-start gap-2 text-red-400 text-sm">
                        <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                        <span>{result.error}</span>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Actions */}
              {!result?.success && (
                <button
                  onClick={handleUpload}
                  disabled={!file || uploading}
                  className={`
                    w-full py-4 rounded-2xl font-black text-sm transition-all flex items-center justify-center gap-2
                    ${file && !uploading
                      ? 'bg-indigo-600 text-white hover:scale-[1.02] shadow-lg shadow-indigo-600/20 active:scale-95'
                      : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    }
                  `}
                >
                  {uploading ? (
                    <><Loader className="w-4 h-4 animate-spin" /> Subiendo...</>
                  ) : (
                    <><Upload className="w-4 h-4" /> DESPLEGAR SITIO</>
                  )}
                </button>
              )}

              {result?.success && (
                <button
                  onClick={handleClose}
                  className="w-full py-4 rounded-2xl font-black text-sm bg-gray-100 text-gray-900 hover:bg-gray-200 transition-all"
                >
                  Cerrar
                </button>
              )}

              {/* Info footer */}
              <div className="text-[10px] text-gray-600 text-center leading-relaxed">
                El ZIP se extrae y se publica automáticamente.<br />
                Compatible con HTML, CSS, JS, PHP y sitios estáticos.
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default ZipUploadModal;
