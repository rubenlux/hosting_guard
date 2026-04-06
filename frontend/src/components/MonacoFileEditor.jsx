import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import {
  X, ChevronRight, Folder, FolderOpen, File, Save,
  Loader, AlertCircle, Home, ArrowLeft, RefreshCw,
} from 'lucide-react';
import { listFiles, readFile, saveFile } from '../services/api';

// Monaco cargado con lazy loading — ~3MB, no debe bloquear el dashboard inicial
const MonacoEditor = lazy(() =>
  import('@monaco-editor/react').then((m) => ({ default: m.default }))
);

// ── Language map ──────────────────────────────────────────────────────────────
const EXT_LANG = {
  '.html': 'html',  '.htm': 'html',
  '.css':  'css',
  '.js':   'javascript', '.jsx': 'javascript',
  '.ts':   'typescript', '.tsx': 'typescript',
  '.php':  'php',
  '.json': 'json',
  '.md':   'markdown',
  '.yml':  'yaml',   '.yaml': 'yaml',
  '.xml':  'xml',
  '.svg':  'xml',
  '.txt':  'plaintext',
};

const EXT_COLOR = {
  '.html': 'text-orange-400', '.htm': 'text-orange-400',
  '.css':  'text-blue-400',
  '.js':   'text-yellow-400', '.jsx': 'text-yellow-400',
  '.ts':   'text-blue-300',   '.tsx': 'text-blue-300',
  '.php':  'text-purple-400',
  '.json': 'text-green-400',  '.yml': 'text-green-400', '.yaml': 'text-green-400',
  '.md':   'text-gray-300',
  '.svg':  'text-pink-400',
};

function extLang(ext)  { return EXT_LANG[ext]  || 'plaintext'; }
function extColor(ext) { return EXT_COLOR[ext] || 'text-gray-400'; }

function formatSize(bytes) {
  if (bytes == null) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Monaco editor options (memoized outside component to avoid re-render) ────
const EDITOR_OPTIONS = {
  fontSize:        13,
  lineNumbers:     'on',
  minimap:         { enabled: false },
  wordWrap:        'on',
  scrollBeyondLastLine: false,
  automaticLayout: true,           // adapta al resize del panel
  tabSize:         2,
  renderLineHighlight: 'line',
  fontFamily:      "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
  padding:         { top: 16, bottom: 16 },
};

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
          <button onClick={() => onNavigate(crumb.path)} className="hover:text-white transition-colors">
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
        ${!item.editable && !isDir ? 'opacity-40 cursor-default' : 'cursor-pointer'}
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
export default function MonacoFileEditor({ hosting, onClose, readOnly = false }) {
  const [currentPath, setCurrentPath]   = useState('');
  const [breadcrumb, setBreadcrumb]     = useState([]);
  const [items, setItems]               = useState([]);
  const [openFile, setOpenFile]         = useState(null);  // { path, name, ext }
  const [content, setContent]           = useState('');
  const [dirty, setDirty]               = useState(false);
  const [dirLoading, setDirLoading]     = useState(false);
  const [fileLoading, setFileLoading]   = useState(false);
  const [saving, setSaving]             = useState(false);
  const [error, setError]               = useState(null);

  // Auto-save debounce: guarda 2s después de que el usuario deja de escribir
  const autoSaveTimer = useRef(null);

  const loadDir = useCallback(async (path) => {
    setDirLoading(true);
    setError(null);
    try {
      const data = await listFiles(hosting.hosting_id, path);
      setItems(data.items);
      setBreadcrumb(data.breadcrumb);
      setCurrentPath(path);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Error cargando directorio');
    } finally {
      setDirLoading(false);
    }
  }, [hosting.hosting_id]);

  useEffect(() => { loadDir(''); }, [loadDir]);

  // Cleanup auto-save timer on unmount
  useEffect(() => () => clearTimeout(autoSaveTimer.current), []);

  const handleItemClick = async (item) => {
    if (item.type === 'dir') {
      if (dirty && !window.confirm('Hay cambios sin guardar. ¿Continuar?')) return;
      clearTimeout(autoSaveTimer.current);
      setDirty(false);
      setOpenFile(null);
      loadDir(item.path);
      return;
    }
    if (!item.editable) return;
    if (dirty && !window.confirm('Hay cambios sin guardar. ¿Continuar?')) return;

    clearTimeout(autoSaveTimer.current);
    setFileLoading(true);
    setError(null);
    try {
      const data = await readFile(hosting.hosting_id, item.path);
      setOpenFile({ path: item.path, name: item.name, ext: item.ext });
      setContent(data.content);
      setDirty(false);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Error leyendo archivo');
    } finally {
      setFileLoading(false);
    }
  };

  const handleNavigate = (path) => {
    if (dirty && !window.confirm('Hay cambios sin guardar. ¿Continuar?')) return;
    clearTimeout(autoSaveTimer.current);
    setDirty(false);
    setOpenFile(null);
    loadDir(path);
  };

  const handleBack = () => {
    if (breadcrumb.length === 0) return;
    const parent = breadcrumb.length > 1
      ? breadcrumb[breadcrumb.length - 2].path
      : '';
    handleNavigate(parent);
  };

  const doSave = useCallback(async (currentContent) => {
    if (!openFile) return;
    setSaving(true);
    setError(null);
    try {
      await saveFile(hosting.hosting_id, openFile.path, currentContent);
      setDirty(false);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Error guardando archivo');
    } finally {
      setSaving(false);
    }
  }, [hosting.hosting_id, openFile]);

  const handleEditorChange = (value) => {
    if (readOnly) return;
    setContent(value ?? '');
    setDirty(true);
    // Auto-save: 2s de inactividad
    clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = setTimeout(() => doSave(value ?? ''), 2000);
  };

  // Ctrl+S / Cmd+S — Monaco intercepta antes de que llegue a window,
  // así que lo registramos con addCommand dentro del editor (ver onMount).
  const handleEditorMount = (editor, monaco) => {
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      clearTimeout(autoSaveTimer.current);
      doSave(editor.getValue());
    });
  };

  const handleManualSave = () => {
    clearTimeout(autoSaveTimer.current);
    doSave(content);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-[#0d0d0d] border border-white/10 rounded-2xl w-full max-w-7xl h-[90vh] flex flex-col shadow-2xl overflow-hidden">

        {/* ── Header ── */}
        <div className="flex items-center gap-3 px-5 py-3.5 border-b border-white/5 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
            <FolderOpen className="w-4 h-4 text-blue-400" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-white">Editor de Archivos</div>
            <div className="text-xs text-gray-500 font-mono truncate">{hosting.name}</div>
          </div>

          {/* Status pill */}
          {saving && (
            <div className="flex items-center gap-1.5 text-[11px] text-accent bg-accent/10 px-2.5 py-1 rounded-lg">
              <Loader className="w-3 h-3 animate-spin" /> Guardando…
            </div>
          )}
          {!saving && dirty && (
            <div className="text-[11px] text-warn bg-warn/10 px-2.5 py-1 rounded-lg font-bold">
              Sin guardar
            </div>
          )}
          {!saving && !dirty && openFile && (
            <div className="text-[11px] text-green-500 bg-green-500/10 px-2.5 py-1 rounded-lg">
              Guardado
            </div>
          )}

          <div className="hidden sm:flex items-center gap-1.5 text-[10px] text-gray-600 bg-white/5 px-2.5 py-1 rounded-lg">
            Auto-save · Ctrl+S · Solo ZIP/GitHub
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-white/5 hover:bg-danger/20 hover:text-danger text-gray-400 flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* ── Body ── */}
        <div className="flex flex-1 overflow-hidden">

          {/* Left — file tree */}
          <div className="w-60 border-r border-white/5 flex flex-col bg-[#090909] shrink-0">
            {/* Tree toolbar */}
            <div className="flex items-center gap-1 px-2 py-2 border-b border-white/5 shrink-0">
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
                disabled={dirLoading}
                className="w-7 h-7 rounded-lg hover:bg-white/5 text-gray-500 hover:text-white flex items-center justify-center transition-colors"
                title="Recargar"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${dirLoading ? 'animate-spin text-accent' : ''}`} />
              </button>
              <div className="flex-1 min-w-0 ml-1 overflow-hidden">
                <Breadcrumb breadcrumb={breadcrumb} onNavigate={handleNavigate} />
              </div>
            </div>

            {/* Items */}
            <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
              {dirLoading && items.length === 0 ? (
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

          {/* Right — Monaco editor */}
          <div className="flex-1 flex flex-col overflow-hidden bg-[#1e1e1e]">
            {fileLoading ? (
              <div className="flex-1 flex items-center justify-center">
                <Loader className="w-6 h-6 animate-spin text-accent" />
              </div>
            ) : openFile ? (
              <>
                {/* Tab bar */}
                <div className="flex items-center gap-3 px-4 py-2 border-b border-white/5 bg-[#252526] shrink-0">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <File className={`w-3.5 h-3.5 shrink-0 ${extColor(openFile.ext)}`} />
                    <span className="text-xs font-mono text-white truncate">
                      {openFile.name}
                      {dirty && <span className="ml-1.5 text-gray-500">●</span>}
                    </span>
                  </div>
                  {readOnly ? (
                    <span className="text-[10px] text-amber-400 bg-amber-400/10 px-2 py-1 rounded font-bold">Solo lectura — modo soporte</span>
                  ) : (
                    <button
                      onClick={handleManualSave}
                      disabled={!dirty || saving}
                      className="flex items-center gap-1.5 px-3 py-1 rounded text-[11px] font-bold transition-colors
                        bg-accent/10 text-accent hover:bg-accent hover:text-black
                        disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      <Save className="w-3 h-3" /> Guardar
                    </button>
                  )}
                </div>

                {/* Monaco */}
                <div className="flex-1 overflow-hidden">
                  <Suspense fallback={
                    <div className="flex items-center justify-center h-full">
                      <Loader className="w-6 h-6 animate-spin text-accent" />
                    </div>
                  }>
                    <MonacoEditor
                      height="100%"
                      language={extLang(openFile.ext)}
                      value={content}
                      theme="vs-dark"
                      options={EDITOR_OPTIONS}
                      onChange={handleEditorChange}
                      onMount={handleEditorMount}
                    />
                  </Suspense>
                </div>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-gray-600 gap-3">
                <File className="w-12 h-12 opacity-10" />
                <div className="text-sm">Seleccioná un archivo para editarlo</div>
                <div className="text-xs opacity-50">
                  .html .css .js .ts .php .json .md .yml y más
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Error bar */}
        {error && (
          <div className="flex items-center gap-2 px-5 py-2.5 bg-danger/10 border-t border-danger/20 text-danger text-xs shrink-0">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
            <button onClick={() => setError(null)} className="ml-auto hover:text-danger/60">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
