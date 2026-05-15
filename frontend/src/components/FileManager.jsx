import { useState, useEffect, useCallback } from 'react';
import {
  X, ChevronRight, Folder, FolderOpen, File, Save,
  Loader, AlertCircle, Home, ArrowLeft, RefreshCw,
} from 'lucide-react';
import { listFiles, readFile, saveFile } from '../services/api';
import { isEditableTarget, isClipboardShortcut } from '../utils/keyboard';

// Extensiones que reciben resaltado de color en el árbol
const EXT_COLOR = {
  '.html': 'text-orange-400', '.htm': 'text-orange-400',
  '.css':  'text-blue-400',
  '.js':   'text-yellow-400', '.jsx': 'text-yellow-400', '.ts': 'text-blue-300', '.tsx': 'text-blue-300',
  '.php':  'text-purple-400',
  '.json': 'text-green-400', '.yml': 'text-green-400', '.yaml': 'text-green-400',
  '.md':   'text-gray-300',
  '.svg':  'text-pink-400',
};

function extColor(ext) {
  return EXT_COLOR[ext] || 'text-gray-400';
}

function formatSize(bytes) {
  if (bytes == null) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Breadcrumb ────────────────────────────────────────────────────────────────
function Breadcrumb({ breadcrumb, onNavigate }) {
  return (
    <div className="flex items-center gap-1 text-xs font-mono text-gray-400 overflow-x-auto whitespace-nowrap">
      <button
        onClick={() => onNavigate('')}
        className="hover:text-white transition-colors flex items-center gap-1 shrink-0"
      >
        <Home className="w-3 h-3" /> raíz
      </button>
      {breadcrumb.map((crumb) => (
        <span key={crumb.path} className="flex items-center gap-1 shrink-0">
          <ChevronRight className="w-3 h-3 text-gray-600" />
          <button
            onClick={() => onNavigate(crumb.path)}
            className="hover:text-white transition-colors"
          >
            {crumb.name}
          </button>
        </span>
      ))}
    </div>
  );
}

// ── File tree item ────────────────────────────────────────────────────────────
function FileItem({ item, isOpen, onClick }) {
  const isDir = item.type === 'dir';
  return (
    <button
      onClick={() => onClick(item)}
      className={`w-full flex items-center gap-2 px-3 py-1.5 text-left rounded-lg transition-colors group
        ${isOpen ? 'bg-accent/10 text-accent' : 'hover:bg-white/5 text-gray-300'}
        ${!item.editable && !isDir ? 'opacity-50 cursor-default' : 'cursor-pointer'}
      `}
      title={!item.editable && !isDir ? 'Archivo no editable' : ''}
    >
      {isDir
        ? (isOpen
            ? <FolderOpen className="w-4 h-4 text-yellow-500 shrink-0" />
            : <Folder className="w-4 h-4 text-yellow-600 shrink-0" />)
        : <File className={`w-4 h-4 shrink-0 ${extColor(item.ext)}`} />
      }
      <span className="text-xs font-mono truncate flex-1">{item.name}</span>
      {item.size != null && (
        <span className="text-[10px] text-gray-600 group-hover:text-gray-500 shrink-0">
          {formatSize(item.size)}
        </span>
      )}
      {isDir && <ChevronRight className="w-3 h-3 text-gray-600 shrink-0" />}
    </button>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function FileManager({ hosting, onClose }) {
  const [currentPath, setCurrentPath] = useState('');
  const [breadcrumb, setBreadcrumb]   = useState([]);
  const [items, setItems]             = useState([]);
  const [openFile, setOpenFile]       = useState(null);   // { path, name }
  const [content, setContent]         = useState('');
  const [dirty, setDirty]             = useState(false);
  const [loading, setLoading]         = useState(false);
  const [saving, setSaving]           = useState(false);
  const [error, setError]             = useState(null);

  const loadDir = useCallback(async (path) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listFiles(hosting.hosting_id, path);
      setItems(data.items);
      setBreadcrumb(data.breadcrumb);
      setCurrentPath(path);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Error cargando directorio');
    } finally {
      setLoading(false);
    }
  }, [hosting.hosting_id]);

  useEffect(() => { loadDir(''); }, [loadDir]);

  const handleItemClick = async (item) => {
    if (item.type === 'dir') {
      if (dirty && !window.confirm('Hay cambios sin guardar. ¿Continuar?')) return;
      setDirty(false);
      setOpenFile(null);
      loadDir(item.path);
      return;
    }
    if (!item.editable) return;

    if (dirty && !window.confirm('Hay cambios sin guardar. ¿Continuar?')) return;

    setLoading(true);
    setError(null);
    try {
      const data = await readFile(hosting.hosting_id, item.path);
      setOpenFile({ path: item.path, name: item.name, ext: item.ext });
      setContent(data.content);
      setDirty(false);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Error leyendo archivo');
    } finally {
      setLoading(false);
    }
  };

  const handleNavigate = (path) => {
    if (dirty && !window.confirm('Hay cambios sin guardar. ¿Continuar?')) return;
    setDirty(false);
    setOpenFile(null);
    loadDir(path);
  };

  const handleSave = async () => {
    if (!openFile || !dirty) return;
    setSaving(true);
    setError(null);
    try {
      await saveFile(hosting.hosting_id, openFile.path, content);
      setDirty(false);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Error guardando archivo');
    } finally {
      setSaving(false);
    }
  };

  const handleKeyDown = (e) => {
    // Never intercept clipboard shortcuts (Ctrl+C/V/X/A/Z) on editable elements.
    if (isEditableTarget(e.target) && isClipboardShortcut(e)) return;
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      handleSave();
    }
  };

  // Go up one level
  const handleBack = () => {
    if (breadcrumb.length === 0) return;
    const parent = breadcrumb.length > 1
      ? breadcrumb[breadcrumb.length - 2].path
      : '';
    handleNavigate(parent);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-[#0d0d0d] border border-white/10 rounded-2xl w-full max-w-6xl h-[85vh] flex flex-col shadow-2xl overflow-hidden">

        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-white/5 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
            <Folder className="w-4 h-4 text-accent" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-white">Gestor de Archivos</div>
            <div className="text-xs text-gray-500 font-mono truncate">{hosting.name}</div>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-gray-500 bg-white/5 px-2.5 py-1 rounded-lg">
            Solo ZIP upload y GitHub deploy · WordPress no soportado
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-white/5 hover:bg-danger/20 hover:text-danger text-gray-400 flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body: two panels */}
        <div className="flex flex-1 overflow-hidden">

          {/* Left — file tree */}
          <div className="w-64 border-r border-white/5 flex flex-col bg-[#0a0a0a] shrink-0">
            {/* Tree toolbar */}
            <div className="flex items-center gap-1 px-3 py-2 border-b border-white/5 shrink-0">
              <button
                onClick={handleBack}
                disabled={breadcrumb.length === 0}
                className="w-7 h-7 rounded-lg hover:bg-white/5 text-gray-500 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center transition-colors"
                title="Subir un nivel"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => loadDir(currentPath)}
                disabled={loading}
                className="w-7 h-7 rounded-lg hover:bg-white/5 text-gray-500 hover:text-white flex items-center justify-center transition-colors"
                title="Recargar"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-accent' : ''}`} />
              </button>
              <div className="flex-1 min-w-0 ml-1">
                <Breadcrumb breadcrumb={breadcrumb} onNavigate={handleNavigate} />
              </div>
            </div>

            {/* Items list */}
            <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
              {loading && items.length === 0 ? (
                <div className="flex justify-center pt-8">
                  <Loader className="w-5 h-5 animate-spin text-accent" />
                </div>
              ) : items.length === 0 ? (
                <div className="text-[11px] text-gray-600 text-center pt-8">Directorio vacío</div>
              ) : items.map((item) => (
                <FileItem
                  key={item.path}
                  item={item}
                  isOpen={openFile?.path === item.path}
                  onClick={handleItemClick}
                />
              ))}
            </div>
          </div>

          {/* Right — editor */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {openFile ? (
              <>
                {/* Editor toolbar */}
                <div className="flex items-center gap-3 px-4 py-2.5 border-b border-white/5 shrink-0 bg-[#0d0d0d]">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <File className={`w-4 h-4 shrink-0 ${extColor(openFile.ext)}`} />
                    <span className="text-sm font-mono text-white truncate">{openFile.name}</span>
                    {dirty && (
                      <span className="text-[10px] bg-warn/20 text-warn px-1.5 py-0.5 rounded font-bold uppercase shrink-0">
                        Sin guardar
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-gray-600 shrink-0">Ctrl+S para guardar</span>
                  <button
                    onClick={handleSave}
                    disabled={!dirty || saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors
                      bg-accent/10 text-accent hover:bg-accent hover:text-black
                      disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {saving ? <Loader className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    Guardar
                  </button>
                </div>

                {/* Textarea editor */}
                <textarea
                  value={content}
                  onChange={(e) => { setContent(e.target.value); setDirty(true); }}
                  onKeyDown={handleKeyDown}
                  spellCheck={false}
                  className="flex-1 w-full bg-[#080808] text-gray-200 font-mono text-xs leading-relaxed
                    resize-none outline-none px-5 py-4 border-0
                    selection:bg-accent/30"
                  style={{ tabSize: 2 }}
                />
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-gray-600 gap-3">
                <File className="w-10 h-10 opacity-20" />
                <div className="text-sm">Seleccioná un archivo para editarlo</div>
                <div className="text-xs opacity-60">Solo archivos editables: .html .css .js .php .json .md y más</div>
              </div>
            )}
          </div>
        </div>

        {/* Error bar */}
        {error && (
          <div className="flex items-center gap-2 px-5 py-3 bg-danger/10 border-t border-danger/20 text-danger text-xs shrink-0">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
            <button onClick={() => setError(null)} className="ml-auto text-danger/60 hover:text-danger">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
