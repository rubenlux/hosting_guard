import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Save, Globe, EyeOff, RefreshCw, AlertCircle } from 'lucide-react';
import {
  adminGetBlogPost,
  adminCreateBlogPost,
  adminUpdateBlogPost,
  adminPublishBlogPost,
  adminUnpublishBlogPost,
} from '../services/api';

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
      className={`bg-[#0d0d0f] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/20
        focus:outline-none focus:border-white/30 transition ${className}`}
      {...props}
    />
  );
}

function Textarea({ className = '', ...props }) {
  return (
    <textarea
      className={`bg-[#0d0d0f] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/20
        focus:outline-none focus:border-white/30 transition resize-none ${className}`}
      {...props}
    />
  );
}

export default function AdminBlogEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isEdit = Boolean(id);

  const [form, setForm] = useState({
    title: '', slug: '', excerpt: '', content: '',
    cover_image_url: '', category: '', tags: '',
    seo_title: '', seo_description: '',
  });
  const [status, setStatus] = useState('draft');
  const [slugManual, setSlugManual] = useState(false);
  const [loading, setLoading]     = useState(isEdit);
  const [saving, setSaving]       = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError]         = useState(null);

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
      if (field === 'title' && !slugManual) {
        next.slug = slugify(val);
      }
      return next;
    });
  };

  const handleSlugChange = (e) => {
    setSlugManual(true);
    setForm((prev) => ({ ...prev, slug: e.target.value }));
  };

  const handleSave = async (publish = false) => {
    setError(null);
    if (!form.title.trim()) { setError('El título es obligatorio.'); return; }

    const payload = { ...form };
    Object.keys(payload).forEach((k) => { if (payload[k] === '') payload[k] = null; });

    if (publish) setPublishing(true);
    else setSaving(true);

    try {
      let post;
      if (isEdit) {
        post = await adminUpdateBlogPost(id, payload);
      } else {
        post = await adminCreateBlogPost(payload);
      }

      if (publish && post.status !== 'published') {
        await adminPublishBlogPost(post.post_id);
      }

      navigate('/admin/blog');
    } catch (err) {
      const msg = err?.response?.data?.detail;
      setError(Array.isArray(msg) ? msg.map((e) => e.msg).join(', ') : (msg || 'Error al guardar.'));
    } finally {
      setSaving(false);
      setPublishing(false);
    }
  };

  const handleTogglePublish = async () => {
    if (!isEdit) return;
    setPublishing(true);
    try {
      if (status === 'published') {
        await adminUnpublishBlogPost(id);
        setStatus('draft');
      } else {
        await adminPublishBlogPost(id);
        setStatus('published');
      }
    } catch (err) {
      const msg = err?.response?.data?.detail;
      setError(typeof msg === 'string' ? msg : 'Error al cambiar estado.');
    } finally {
      setPublishing(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0d0d0f] flex items-center justify-center text-white/30">
        <RefreshCw size={18} className="animate-spin mr-2" /> Cargando...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0d0d0f] text-white">
      {/* Top bar */}
      <div className="border-b border-white/8 bg-[#111] px-6 py-3 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/admin/blog')}
            className="text-white/40 hover:text-white transition"
          >
            <ArrowLeft size={16} />
          </button>
          <span className="text-sm font-medium">
            {isEdit ? 'Editar artículo' : 'Nuevo artículo'}
          </span>
          {isEdit && (
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
              status === 'published'
                ? 'bg-[#00ff88]/15 text-[#00ff88] border border-[#00ff88]/30'
                : status === 'archived'
                ? 'bg-white/10 text-white/40 border border-white/10'
                : 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30'
            }`}>
              {status === 'published' ? 'Publicado' : status === 'archived' ? 'Archivado' : 'Borrador'}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => handleSave(false)}
            disabled={saving || publishing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs text-white/70 hover:text-white hover:bg-white/10 transition disabled:opacity-40"
          >
            {saving ? <RefreshCw size={12} className="animate-spin" /> : <Save size={12} />}
            Guardar borrador
          </button>

          {isEdit ? (
            <button
              onClick={handleTogglePublish}
              disabled={saving || publishing || status === 'archived'}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition disabled:opacity-40 ${
                status === 'published'
                  ? 'bg-white/5 border border-white/10 text-white/60 hover:bg-white/10'
                  : 'bg-[#00ff88]/10 border border-[#00ff88]/30 text-[#00ff88] hover:bg-[#00ff88]/20'
              }`}
            >
              {publishing
                ? <RefreshCw size={12} className="animate-spin" />
                : status === 'published' ? <EyeOff size={12} /> : <Globe size={12} />
              }
              {status === 'published' ? 'Despublicar' : 'Publicar'}
            </button>
          ) : (
            <button
              onClick={() => handleSave(true)}
              disabled={saving || publishing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#00ff88]/10 border border-[#00ff88]/30 text-xs text-[#00ff88] hover:bg-[#00ff88]/20 transition disabled:opacity-40"
            >
              {publishing ? <RefreshCw size={12} className="animate-spin" /> : <Globe size={12} />}
              Publicar
            </button>
          )}
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Main content */}
        <div className="lg:col-span-2 flex flex-col gap-5">
          {error && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              {error}
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

          <Field label="Contenido" required hint="HTML permitido. Scripts, iframes y handlers on* son eliminados automáticamente.">
            <Textarea
              value={form.content}
              onChange={set('content')}
              placeholder="<h2>Introducción</h2>&#10;<p>Escribe el contenido en HTML...</p>"
              rows={18}
              className="font-mono text-sm"
            />
          </Field>
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

            <Field label="URL de imagen de portada">
              <Input
                value={form.cover_image_url}
                onChange={set('cover_image_url')}
                placeholder="https://..."
              />
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

        </div>
      </div>
    </div>
  );
}
