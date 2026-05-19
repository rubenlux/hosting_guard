import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Save, Globe, EyeOff, RefreshCw, AlertCircle, AlertTriangle,
  Upload, ImageIcon, X, Eye, Home, BookOpen,
  ExternalLink, CheckCircle, ChevronRight,
} from 'lucide-react';
import {
  adminGetBlogPost,
  adminCreateBlogPost,
  adminUpdateBlogPost,
  adminPublishBlogPost,
  adminUnpublishBlogPost,
  adminUploadBlogMedia,
} from '../services/api';

// ── Utilities ──────────────────────────────────────────────────────────────────

function slugify(text) {
  return (text || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/[\s_]+/g, '-')
    .replace(/-+/g, '-')
    .slice(0, 120) || 'post';
}

function escHtml(s) {
  return (s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function applyInline(s) {
  return s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

function simpleToHtml(text) {
  const lines = (text || '').split('\n');
  const out = [];
  let paraLines = [];
  let listItems = [];

  const flushPara = () => {
    if (paraLines.length) {
      out.push(`<p>${applyInline(escHtml(paraLines.join(' ')))}</p>`);
      paraLines = [];
    }
  };
  const flushList = () => {
    if (listItems.length) {
      out.push(
        '<ul>\n' +
        listItems.map(i => `  <li>${applyInline(escHtml(i))}</li>`).join('\n') +
        '\n</ul>'
      );
      listItems = [];
    }
  };

  for (const line of lines) {
    const t = line.trim();
    if (!t) {
      flushPara();
      flushList();
    } else if (t.startsWith('### ')) {
      flushPara(); flushList();
      out.push(`<h3>${applyInline(escHtml(t.slice(4)))}</h3>`);
    } else if (t.startsWith('## ')) {
      flushPara(); flushList();
      out.push(`<h2>${applyInline(escHtml(t.slice(3)))}</h2>`);
    } else if (t.startsWith('# ')) {
      flushPara(); flushList();
      out.push(`<h1>${applyInline(escHtml(t.slice(2)))}</h1>`);
    } else if (t.startsWith('- ') || t.startsWith('* ')) {
      flushPara();
      listItems.push(t.slice(2));
    } else {
      flushList();
      paraLines.push(t);
    }
  }
  flushPara();
  flushList();
  return out.join('\n');
}

function looksLikeHtml(text) {
  return /<[a-z][^>]*>/i.test(text || '');
}

function hasInvalidImages(content) {
  return /PEGAR_AQUI_LA_URL_DE_LA_IMAGEN_SUBIDA|src=""|src='#'|src="#"/.test(content || '');
}

// ── Small components ───────────────────────────────────────────────────────────

function Field({ label, required, children, hint }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium text-white/60">
        {label}{required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      {children}
      {hint && <p className="text-[10px] text-white/30">{hint}</p>}
    </div>
  );
}

function Input({ className = '', ...props }) {
  return (
    <input
      className={`bg-[#0d0d0f] border border-white/10 rounded-lg px-3 py-2 text-sm text-white
        placeholder-white/20 focus:outline-none focus:border-white/30 transition ${className}`}
      {...props}
    />
  );
}

const Textarea = React.forwardRef(function Textarea({ className = '', ...props }, ref) {
  return (
    <textarea
      ref={ref}
      className={`bg-[#0d0d0f] border border-white/10 rounded-lg px-3 py-2 text-sm text-white
        placeholder-white/20 focus:outline-none focus:border-white/30 transition resize-none ${className}`}
      {...props}
    />
  );
});

// ── Preview modal ──────────────────────────────────────────────────────────────

function PreviewModal({ form, contentMode, onClose }) {
  const html = contentMode === 'simple' ? simpleToHtml(form.content) : (form.content || '');

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/80 backdrop-blur-sm overflow-y-auto py-8 px-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="relative bg-[#0d0d0f] border border-white/10 rounded-2xl w-full max-w-3xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/8 sticky top-0 bg-[#0d0d0f] rounded-t-2xl z-10">
          <div className="flex items-center gap-2">
            <Eye size={14} className="text-[#00ff88]" />
            <span className="text-sm font-semibold">Vista previa</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-white/40">
              Sin guardar
            </span>
          </div>
          <button onClick={onClose} className="text-white/40 hover:text-white transition p-1 rounded">
            <X size={16} />
          </button>
        </div>

        {form.cover_image_url && (
          <div className="w-full h-52 overflow-hidden bg-white/5">
            <img
              src={form.cover_image_url}
              alt={form.title}
              className="w-full h-full object-cover"
              onError={(e) => { e.target.parentElement.style.display = 'none'; }}
            />
          </div>
        )}

        <div className="px-6 py-8">
          {form.category && (
            <span className="text-[10px] font-semibold uppercase tracking-widest text-[#00ff88]/70 mb-3 block">
              {form.category}
            </span>
          )}
          <h1 className="text-3xl font-black text-white mb-4 leading-tight">
            {form.title || <span className="text-white/20 italic">Sin título</span>}
          </h1>
          {form.excerpt && (
            <p className="text-lg text-white/60 mb-8 border-l-2 border-[#00ff88]/30 pl-4 leading-relaxed">
              {form.excerpt}
            </p>
          )}
          <div className="prose-blog" dangerouslySetInnerHTML={{ __html: html }} />
          {form.tags && (
            <div className="flex flex-wrap gap-2 mt-10 pt-6 border-t border-white/8">
              {form.tags.split(',').map(t => t.trim()).filter(Boolean).map(tag => (
                <span key={tag} className="text-[11px] px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-white/50">
                  #{tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main editor ────────────────────────────────────────────────────────────────

export default function AdminBlogEditor() {
  const { id }    = useParams();
  const navigate  = useNavigate();
  const isEdit    = Boolean(id);

  const [form, setForm] = useState({
    title: '', slug: '', excerpt: '', content: '',
    cover_image_url: '', category: '', tags: '',
    seo_title: '', seo_description: '',
  });
  const [status,      setStatus]      = useState('draft');
  const [slugManual,  setSlugManual]  = useState(false);
  const [loading,     setLoading]     = useState(isEdit);
  const [saving,      setSaving]      = useState(false);
  const [publishing,  setPublishing]  = useState(false);
  const [error,       setError]       = useState(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const [contentMode, setContentMode] = useState('simple');
  const [htmlLocked,  setHtmlLocked]  = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const [uploadingCover,   setUploadingCover]   = useState(false);
  const [uploadingContent, setUploadingContent] = useState(false);
  const [uploadError,      setUploadError]      = useState(null);

  const coverInputRef      = useRef(null);
  const contentInputRef    = useRef(null);
  const contentTextareaRef = useRef(null);

  const load = useCallback(async () => {
    if (!isEdit) return;
    try {
      const post = await adminGetBlogPost(id);
      setForm({
        title:           post.title           || '',
        slug:            post.slug            || '',
        excerpt:         post.excerpt         || '',
        content:         post.content         || '',
        cover_image_url: post.cover_image_url || '',
        category:        post.category        || '',
        tags:            post.tags            || '',
        seo_title:       post.seo_title       || '',
        seo_description: post.seo_description || '',
      });
      setStatus(post.status || 'draft');
      setSlugManual(true);
      if (looksLikeHtml(post.content)) {
        setContentMode('html');
        setHtmlLocked(true);
      }
    } catch {
      setError('No se pudo cargar el post.');
    } finally {
      setLoading(false);
    }
  }, [id, isEdit]);

  useEffect(() => { load(); }, [load]);

  const set = (field) => (e) => {
    const val = e.target.value;
    setForm((prev) => {
      const next = { ...prev, [field]: val };
      if (field === 'title' && !slugManual) next.slug = slugify(val);
      return next;
    });
  };

  const handleSlugChange = (e) => {
    setSlugManual(true);
    setForm((prev) => ({ ...prev, slug: e.target.value }));
  };

  const flashSuccess = () => {
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 3000);
  };

  const buildPayload = () => {
    const payload = { ...form };
    if (contentMode === 'simple') payload.content = simpleToHtml(form.content);
    Object.keys(payload).forEach((k) => { if (payload[k] === '') payload[k] = null; });
    return payload;
  };

  const handleSave = async () => {
    setError(null);
    if (!form.title.trim()) { setError('El título es obligatorio.'); return; }
    setSaving(true);
    try {
      const payload = buildPayload();
      if (isEdit) {
        await adminUpdateBlogPost(id, payload);
        flashSuccess();
      } else {
        const post = await adminCreateBlogPost(payload);
        navigate(`/admin/blog/${post.post_id}/edit`, { replace: true });
      }
    } catch (err) {
      const msg = err?.response?.data?.detail;
      setError(Array.isArray(msg) ? msg.map((e) => e.msg).join(', ') : (msg || 'Error al guardar.'));
    } finally {
      setSaving(false);
    }
  };

  const handlePublish = async () => {
    setError(null);
    if (!form.title.trim()) { setError('El título es obligatorio.'); return; }
    if (hasInvalidImages(form.content)) {
      setError('Hay una imagen con URL inválida. Corregila antes de publicar.');
      return;
    }
    setPublishing(true);
    try {
      const payload = buildPayload();
      let post = isEdit
        ? await adminUpdateBlogPost(id, payload)
        : await adminCreateBlogPost(payload);

      if (post.status !== 'published') {
        await adminPublishBlogPost(post.post_id);
      }
      setStatus('published');
      flashSuccess();
      if (!isEdit) navigate(`/admin/blog/${post.post_id}/edit`, { replace: true });
    } catch (err) {
      const msg = err?.response?.data?.detail;
      setError(Array.isArray(msg) ? msg.map((e) => e.msg).join(', ') : (msg || 'Error al publicar.'));
    } finally {
      setPublishing(false);
    }
  };

  const handleHideFromBlog = async () => {
    if (!isEdit) return;
    setPublishing(true);
    setError(null);
    try {
      await adminUnpublishBlogPost(id);
      setStatus('draft');
      flashSuccess();
    } catch (err) {
      const msg = err?.response?.data?.detail;
      setError(typeof msg === 'string' ? msg : 'Error al ocultar el artículo.');
    } finally {
      setPublishing(false);
    }
  };

  const handleUploadCover = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploadingCover(true);
    try {
      const result = await adminUploadBlogMedia(file, {
        postSlug:  form.slug  || undefined,
        postTitle: form.title || undefined,
        imageRole: 'cover',
        imageAlt:  form.seo_title || form.title || undefined,
      });
      setForm((prev) => ({ ...prev, cover_image_url: result.url }));
    } catch (err) {
      const msg = err?.response?.data?.detail;
      setUploadError(typeof msg === 'string' ? msg : 'Error al subir la imagen.');
    } finally {
      setUploadingCover(false);
      e.target.value = '';
    }
  };

  const handleUploadContent = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploadingContent(true);
    try {
      const result = await adminUploadBlogMedia(file, {
        postSlug:  form.slug  || undefined,
        postTitle: form.title || undefined,
        imageRole: 'inline',
        imageAlt:  form.title || undefined,
        imageName: 'imagen',
      });
      const altText = form.title || '';
      const snippet = `<figure>\n  <img src="${result.url}" alt="${altText}" loading="lazy" decoding="async" />\n  <figcaption>Descripción de la imagen</figcaption>\n</figure>`;
      insertAtCursor(snippet);
    } catch (err) {
      const msg = err?.response?.data?.detail;
      setUploadError(typeof msg === 'string' ? msg : 'Error al subir la imagen.');
    } finally {
      setUploadingContent(false);
      e.target.value = '';
    }
  };

  const insertAtCursor = (snippet) => {
    const ta = contentTextareaRef.current;
    if (ta) {
      const start  = ta.selectionStart ?? ta.value.length;
      const end    = ta.selectionEnd   ?? ta.value.length;
      const before = ta.value.slice(0, start);
      const after  = ta.value.slice(end);
      const sep    = before && !before.endsWith('\n') ? '\n' : '';
      const newVal = before + sep + snippet + '\n' + after;
      setForm((prev) => ({ ...prev, content: newVal }));
      requestAnimationFrame(() => {
        const pos = before.length + sep.length + snippet.length + 1;
        ta.setSelectionRange(pos, pos);
        ta.focus();
      });
    } else {
      setForm((prev) => ({ ...prev, content: (prev.content || '') + '\n' + snippet + '\n' }));
    }
  };

  const handleInsertCoverInContent = () => {
    if (!form.cover_image_url) return;
    const snippet = `<figure>\n  <img src="${form.cover_image_url}" alt="${form.title || ''}" loading="lazy" decoding="async" />\n  <figcaption></figcaption>\n</figure>`;
    insertAtCursor(snippet);
  };

  const isBusy       = saving || publishing || uploadingCover || uploadingContent;
  const isPublished  = status === 'published';
  const isArchived   = status === 'archived';

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0d0d0f] flex items-center justify-center text-white/30">
        <RefreshCw size={18} className="animate-spin mr-2" /> Cargando...
      </div>
    );
  }

  return (
    <>
      {showPreview && (
        <PreviewModal form={form} contentMode={contentMode} onClose={() => setShowPreview(false)} />
      )}

      <div className="min-h-screen bg-[#0d0d0f] text-white">

        {/* ── Header ── */}
        <div className="border-b border-white/8 bg-[#111] sticky top-0 z-10">
          <div className="px-4 sm:px-6 py-3 flex items-center justify-between gap-3 flex-wrap">

            {/* Breadcrumb */}
            <div className="flex items-center gap-1 text-xs text-white/40 min-w-0">
              <button
                onClick={() => navigate('/dashboard')}
                className="flex items-center gap-1.5 hover:text-white transition shrink-0"
              >
                <Home size={13} />
                <span className="hidden sm:inline">Dashboard</span>
              </button>
              <ChevronRight size={11} className="shrink-0 opacity-40" />
              <button
                onClick={() => navigate('/admin/blog')}
                className="flex items-center gap-1.5 hover:text-white transition shrink-0"
              >
                <BookOpen size={13} />
                <span className="hidden sm:inline">Blog CMS</span>
              </button>
              <ChevronRight size={11} className="shrink-0 opacity-40" />
              <span className="text-white/70 truncate max-w-[140px] sm:max-w-[220px]">
                {form.title || (isEdit ? `Artículo #${id}` : 'Nuevo artículo')}
              </span>
              {isEdit && (
                <span className={`ml-1.5 shrink-0 text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                  isPublished
                    ? 'bg-[#00ff88]/15 text-[#00ff88] border border-[#00ff88]/30'
                    : isArchived
                    ? 'bg-white/10 text-white/40 border border-white/10'
                    : 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30'
                }`}>
                  {isPublished ? 'Publicado' : isArchived ? 'Archivado' : 'Borrador'}
                </span>
              )}
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 shrink-0">
              {isEdit && isPublished && form.slug && (
                <a
                  href={`/blog/${form.slug}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10
                    text-xs text-white/60 hover:text-white hover:bg-white/10 transition"
                >
                  <ExternalLink size={12} /> Ver artículo
                </a>
              )}

              <button
                onClick={() => setShowPreview(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10
                  text-xs text-white/60 hover:text-white hover:bg-white/10 transition"
              >
                <Eye size={12} />
                <span className="hidden sm:inline">Vista previa</span>
              </button>

              <button
                onClick={handleSave}
                disabled={isBusy}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10
                  text-xs text-white/70 hover:text-white hover:bg-white/10 transition disabled:opacity-40"
              >
                {saving ? <RefreshCw size={12} className="animate-spin" /> : <Save size={12} />}
                {isEdit ? 'Guardar cambios' : 'Guardar borrador'}
              </button>

              {isEdit && isPublished ? (
                <button
                  onClick={handleHideFromBlog}
                  disabled={isBusy}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10
                    text-xs text-white/60 hover:text-white hover:bg-white/10 transition disabled:opacity-40"
                >
                  {publishing ? <RefreshCw size={12} className="animate-spin" /> : <EyeOff size={12} />}
                  Ocultar del blog
                </button>
              ) : !isArchived && (
                <button
                  onClick={handlePublish}
                  disabled={isBusy}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#00ff88]/10 border border-[#00ff88]/30
                    text-xs text-[#00ff88] hover:bg-[#00ff88]/20 transition disabled:opacity-40"
                >
                  {publishing ? <RefreshCw size={12} className="animate-spin" /> : <Globe size={12} />}
                  Publicar
                </button>
              )}
            </div>
          </div>

          {saveSuccess && (
            <div className="flex items-center gap-2 px-5 py-2 bg-[#00ff88]/8 border-t border-[#00ff88]/20 text-[#00ff88] text-xs">
              <CheckCircle size={12} /> Cambios guardados correctamente.
            </div>
          )}
        </div>

        {/* ── Body ── */}
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Main column */}
          <div className="lg:col-span-2 flex flex-col gap-5">

            {error && (
              <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {uploadError && (
              <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-orange-500/10 border border-orange-500/30 text-orange-400 text-xs">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            {hasInvalidImages(form.content) && (
              <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 text-xs">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                Hay una imagen interna con URL inválida. Corregila antes de publicar.
              </div>
            )}

            <Field label="Título" required>
              <Input
                value={form.title}
                onChange={set('title')}
                placeholder="Título del artículo"
                className="text-base"
              />
            </Field>

            <Field label="Slug (URL)" hint={`hostingguard.lat/blog/${form.slug || 'mi-articulo'}`}>
              <Input
                value={form.slug}
                onChange={handleSlugChange}
                placeholder="mi-articulo"
                className="font-mono text-[#00ff88]/80"
              />
            </Field>

            <Field label="Extracto" hint="Resumen breve que aparece en el listado (máx. 300 chars)">
              <Textarea
                value={form.excerpt}
                onChange={set('excerpt')}
                placeholder="Breve descripción del artículo..."
                rows={3}
                maxLength={300}
              />
            </Field>

            {/* Content block */}
            <div className="flex flex-col gap-1.5">
              {/* Label row */}
              <div className="flex items-center justify-between gap-2">
                <label className="text-xs font-medium text-white/60">
                  Contenido<span className="text-red-400 ml-0.5">*</span>
                </label>
                {!htmlLocked ? (
                  <div className="flex items-center gap-0.5 bg-white/5 border border-white/10 rounded-md p-0.5">
                    <button
                      onClick={() => setContentMode('simple')}
                      className={`px-2.5 py-1 rounded text-[10px] font-medium transition ${
                        contentMode === 'simple'
                          ? 'bg-[#00ff88]/15 text-[#00ff88]'
                          : 'text-white/40 hover:text-white/70'
                      }`}
                    >
                      Texto simple
                    </button>
                    <button
                      onClick={() => setContentMode('html')}
                      className={`px-2.5 py-1 rounded text-[10px] font-medium transition ${
                        contentMode === 'html'
                          ? 'bg-white/10 text-white'
                          : 'text-white/40 hover:text-white/70'
                      }`}
                    >
                      HTML avanzado
                    </button>
                  </div>
                ) : (
                  <span className="text-[10px] px-2 py-0.5 rounded bg-white/5 border border-white/10 text-white/40">
                    HTML avanzado
                  </span>
                )}
              </div>

              {/* Mode hint */}
              <p className="text-[10px] text-white/30">
                {contentMode === 'simple'
                  ? '## Título h2  · ### h3  · - Lista  · **negrita**  · doble enter = párrafo'
                  : 'HTML sanitizado — scripts, iframes y atributos on* son eliminados automáticamente.'
                }
              </p>

              {/* Toolbar */}
              <div className="flex items-center flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => contentInputRef.current?.click()}
                  disabled={uploadingContent}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/5 border border-white/10
                    text-[11px] text-white/50 hover:text-white hover:bg-white/10 transition disabled:opacity-40"
                >
                  {uploadingContent ? <RefreshCw size={11} className="animate-spin" /> : <ImageIcon size={11} />}
                  Insertar imagen
                </button>
                {form.cover_image_url && (
                  <button
                    type="button"
                    onClick={handleInsertCoverInContent}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/5 border border-white/10
                      text-[11px] text-white/50 hover:text-white hover:bg-white/10 transition"
                  >
                    <Upload size={11} />
                    Usar portada en contenido
                  </button>
                )}
                <input
                  ref={contentInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={handleUploadContent}
                />
              </div>

              <Textarea
                ref={contentTextareaRef}
                value={form.content}
                onChange={set('content')}
                placeholder={
                  contentMode === 'simple'
                    ? '## Introducción\n\nEscribe el contenido aquí...\n\n- Elemento de lista\n\n**texto en negrita**'
                    : '<h2>Introducción</h2>\n<p>Escribe el contenido en HTML...</p>'
                }
                rows={18}
                className={contentMode === 'html' ? 'font-mono text-sm' : 'text-sm'}
              />
            </div>
          </div>

          {/* Sidebar */}
          <div className="flex flex-col gap-4">

            <div className="bg-[#111] border border-white/8 rounded-xl p-4 flex flex-col gap-4">
              <p className="text-xs font-semibold text-white/60 uppercase tracking-wider">Metadatos</p>

              <Field label="Categoría">
                <Input
                  value={form.category}
                  onChange={set('category')}
                  placeholder="ej. Seguridad, WordPress"
                />
              </Field>

              <Field label="Tags" hint="Separados por coma">
                <Input
                  value={form.tags}
                  onChange={set('tags')}
                  placeholder="ej. hosting, wordpress, ssl"
                />
              </Field>

              <Field label="Imagen de portada">
                <div className="flex gap-2">
                  <Input
                    value={form.cover_image_url}
                    onChange={set('cover_image_url')}
                    placeholder="https://..."
                    className="flex-1 min-w-0"
                  />
                  <button
                    type="button"
                    onClick={() => coverInputRef.current?.click()}
                    disabled={uploadingCover}
                    title="Subir imagen de portada"
                    className="shrink-0 flex items-center px-2.5 py-2 rounded-lg bg-white/5 border border-white/10
                      text-white/50 hover:text-white hover:bg-white/10 transition disabled:opacity-40"
                  >
                    {uploadingCover ? <RefreshCw size={13} className="animate-spin" /> : <Upload size={13} />}
                  </button>
                  <input
                    ref={coverInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={handleUploadCover}
                  />
                </div>
              </Field>

              {form.cover_image_url && (
                <img
                  src={form.cover_image_url}
                  alt="Preview portada"
                  className="rounded-lg w-full h-28 object-cover border border-white/8"
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
              )}
            </div>

            <div className="bg-[#111] border border-white/8 rounded-xl p-4 flex flex-col gap-4">
              <p className="text-xs font-semibold text-white/60 uppercase tracking-wider">SEO</p>

              <Field label="Título SEO" hint="Si se deja vacío, se usa el título del artículo">
                <Input
                  value={form.seo_title}
                  onChange={set('seo_title')}
                  placeholder="Título para buscadores"
                />
              </Field>

              <Field label="Descripción SEO" hint="Máx. 160 chars">
                <Textarea
                  value={form.seo_description}
                  onChange={set('seo_description')}
                  placeholder="Descripción para buscadores..."
                  rows={3}
                  maxLength={160}
                />
                <p className="text-[10px] text-white/20 text-right">
                  {(form.seo_description || '').length}/160
                </p>
              </Field>
            </div>

            {/* Mobile: Ver artículo */}
            {isEdit && isPublished && form.slug && (
              <a
                href={`/blog/${form.slug}`}
                target="_blank"
                rel="noopener noreferrer"
                className="sm:hidden flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl
                  bg-white/5 border border-white/10 text-sm text-white/60 hover:text-white hover:bg-white/10 transition"
              >
                <ExternalLink size={14} /> Ver artículo publicado
              </a>
            )}

          </div>
        </div>
      </div>
    </>
  );
}
