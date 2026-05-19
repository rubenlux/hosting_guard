import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PlusCircle, RefreshCw, Pencil, Archive, Eye, EyeOff,
  FileText, Globe, BookOpen, Clock,
} from 'lucide-react';
import {
  adminListBlogPosts,
  adminPublishBlogPost,
  adminUnpublishBlogPost,
  adminArchiveBlogPost,
} from '../services/api';

const STATUS_BADGE = {
  draft:     'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30',
  published: 'bg-[#00ff88]/15 text-[#00ff88] border border-[#00ff88]/30',
  archived:  'bg-white/10 text-white/40 border border-white/10',
};

const STATUS_LABEL = { draft: 'Borrador', published: 'Publicado', archived: 'Archivado' };

const TABS = [
  { key: '',          label: 'Todos',       icon: BookOpen },
  { key: 'published', label: 'Publicados',  icon: Globe },
  { key: 'draft',     label: 'Borradores',  icon: FileText },
  { key: 'archived',  label: 'Archivados',  icon: Archive },
];

function fmtDate(str) {
  if (!str) return '—';
  return new Date(str).toLocaleString('es-AR', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function AdminBlogList() {
  const navigate = useNavigate();
  const [posts, setPosts]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [tab, setTab]         = useState('');
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 50, offset: 0 };
      if (tab) params.status = tab;
      const res = await adminListBlogPosts(params);
      setPosts(res.posts || []);
      setTotal(res.total || 0);
    } catch {
      // silent — keep stale data
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => { load(); }, [load]);

  const handlePublish = async (post) => {
    setActionId(post.post_id);
    try {
      if (post.status === 'published') {
        await adminUnpublishBlogPost(post.post_id);
      } else {
        await adminPublishBlogPost(post.post_id);
      }
      await load();
    } finally {
      setActionId(null);
    }
  };

  const handleArchive = async (post) => {
    if (!window.confirm(`¿Archivar "${post.title}"? El post dejará de ser visible públicamente.`)) return;
    setActionId(post.post_id);
    try {
      await adminArchiveBlogPost(post.post_id);
      await load();
    } finally {
      setActionId(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#0d0d0f] text-white p-6">
      <div className="max-w-6xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold">Blog CMS</h1>
            <p className="text-xs text-white/40 mt-0.5">{total} artículo{total !== 1 ? 's' : ''} en total</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={load}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/5 border border-white/8 text-xs text-white/60 hover:text-white hover:bg-white/10 transition disabled:opacity-40"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              Actualizar
            </button>
            <button
              onClick={() => navigate('/admin/blog/new')}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#00ff88]/10 border border-[#00ff88]/30 text-xs text-[#00ff88] hover:bg-[#00ff88]/20 transition"
            >
              <PlusCircle size={13} />
              Nuevo artículo
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-4 bg-white/5 border border-white/8 rounded-lg p-1 w-fit">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs transition ${
                tab === key
                  ? 'bg-white/10 text-white'
                  : 'text-white/40 hover:text-white/70'
              }`}
            >
              <Icon size={12} />
              {label}
            </button>
          ))}
        </div>

        {/* Table */}
        <div className="bg-[#111] border border-white/8 rounded-xl overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-white/30 text-sm">
              <RefreshCw size={16} className="animate-spin mr-2" />
              Cargando...
            </div>
          ) : posts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-white/30">
              <FileText size={28} className="mb-2 opacity-30" />
              <p className="text-sm">No hay artículos</p>
              <button
                onClick={() => navigate('/admin/blog/new')}
                className="mt-3 text-xs text-[#00ff88]/70 hover:text-[#00ff88] transition"
              >
                + Crear el primero
              </button>
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/8">
                  <th className="text-left px-4 py-3 text-white/40 font-medium">Título</th>
                  <th className="text-left px-4 py-3 text-white/40 font-medium hidden md:table-cell">Categoría</th>
                  <th className="text-left px-4 py-3 text-white/40 font-medium">Estado</th>
                  <th className="text-left px-4 py-3 text-white/40 font-medium hidden lg:table-cell">Publicado</th>
                  <th className="px-4 py-3 text-white/40 font-medium text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {posts.map((post) => (
                  <tr
                    key={post.post_id}
                    className="border-b border-white/5 hover:bg-white/3 transition"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-white/90 truncate max-w-[280px]">{post.title}</div>
                      <div className="text-white/30 font-mono mt-0.5 truncate max-w-[280px]">{post.slug}</div>
                    </td>
                    <td className="px-4 py-3 text-white/50 hidden md:table-cell">
                      {post.category || <span className="text-white/20 italic">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${STATUS_BADGE[post.status] || STATUS_BADGE.draft}`}>
                        {STATUS_LABEL[post.status] || post.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-white/40 hidden lg:table-cell">
                      <div className="flex items-center gap-1">
                        <Clock size={10} />
                        {fmtDate(post.published_at || post.created_at)}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => navigate(`/admin/blog/${post.post_id}/edit`)}
                          title="Editar"
                          className="p-1.5 rounded text-white/40 hover:text-white hover:bg-white/10 transition"
                        >
                          <Pencil size={13} />
                        </button>
                        {post.status !== 'archived' && (
                          <button
                            onClick={() => handlePublish(post)}
                            disabled={actionId === post.post_id}
                            title={post.status === 'published' ? 'Despublicar' : 'Publicar'}
                            className={`p-1.5 rounded transition disabled:opacity-40 ${
                              post.status === 'published'
                                ? 'text-[#00ff88]/60 hover:text-[#00ff88] hover:bg-[#00ff88]/10'
                                : 'text-white/40 hover:text-[#00ff88] hover:bg-[#00ff88]/10'
                            }`}
                          >
                            {post.status === 'published' ? <EyeOff size={13} /> : <Eye size={13} />}
                          </button>
                        )}
                        {post.status !== 'archived' && (
                          <button
                            onClick={() => handleArchive(post)}
                            disabled={actionId === post.post_id}
                            title="Archivar"
                            className="p-1.5 rounded text-white/40 hover:text-red-400 hover:bg-red-500/10 transition disabled:opacity-40"
                          >
                            <Archive size={13} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

      </div>
    </div>
  );
}
