import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, ArrowRight, Calendar, Tag, RefreshCw } from 'lucide-react';
import { listBlogPosts } from '../services/api';

function fmtDate(str) {
  if (!str) return '';
  return new Date(str).toLocaleDateString('es-AR', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

function PostCard({ post }) {
  return (
    <Link
      to={`/blog/${post.slug}`}
      className="group flex flex-col bg-[#111] border border-white/8 rounded-2xl overflow-hidden hover:border-white/20 transition-all duration-200 hover:-translate-y-0.5"
    >
      {post.cover_image_url && (
        <div className="w-full h-44 overflow-hidden bg-white/5">
          <img
            src={post.cover_image_url}
            alt={post.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            onError={(e) => { e.target.parentElement.style.display = 'none'; }}
          />
        </div>
      )}
      <div className="flex flex-col gap-3 p-5 flex-1">
        {post.category && (
          <span className="text-[10px] font-semibold uppercase tracking-widest text-[#00ff88]/70">
            {post.category}
          </span>
        )}
        <h2 className="text-base font-bold text-white leading-snug group-hover:text-[#00ff88] transition-colors line-clamp-2">
          {post.title}
        </h2>
        {post.excerpt && (
          <p className="text-sm text-white/50 leading-relaxed line-clamp-3">{post.excerpt}</p>
        )}
        <div className="mt-auto flex items-center justify-between pt-3 border-t border-white/8">
          <div className="flex items-center gap-1 text-[11px] text-white/30">
            <Calendar size={11} />
            {fmtDate(post.published_at)}
          </div>
          <span className="flex items-center gap-1 text-[11px] text-[#00ff88]/60 group-hover:text-[#00ff88] transition-colors">
            Leer más <ArrowRight size={11} />
          </span>
        </div>
      </div>
    </Link>
  );
}

export default function BlogList() {
  const [posts, setPosts]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset]   = useState(0);
  const LIMIT = 9;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listBlogPosts({ limit: LIMIT, offset })
      .then((res) => {
        if (!cancelled) {
          setPosts(res.posts || []);
          setTotal(res.total || 0);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [offset]);

  return (
    <div className="min-h-screen bg-[#080809] text-white">

      {/* Nav */}
      <header className="border-b border-white/8 bg-[#0d0d0f] sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-[#00ff88]" />
            <span className="font-bold">Hosting<span className="text-[#00ff88]">Guard</span></span>
          </Link>
          <nav className="flex items-center gap-6 text-sm">
            <Link to="/" className="text-white/50 hover:text-white transition">Inicio</Link>
            <Link to="/" className="text-white/50 hover:text-white transition">Acceder</Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="border-b border-white/8 bg-gradient-to-b from-[#111] to-[#080809]">
        <div className="max-w-6xl mx-auto px-6 py-16 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#00ff88]/10 border border-[#00ff88]/20 text-[#00ff88] text-xs font-medium mb-6">
            <Tag size={11} />
            Blog
          </div>
          <h1 className="text-4xl md:text-5xl font-black tracking-tight mb-4">
            Recursos y guías de<br />
            <span className="text-[#00ff88]">hosting gestionado</span>
          </h1>
          <p className="text-white/50 text-lg max-w-xl mx-auto">
            Tutoriales, noticias y consejos para mantener tu sitio rápido, seguro y siempre online.
          </p>
        </div>
      </section>

      {/* Posts grid */}
      <main className="max-w-6xl mx-auto px-6 py-12">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-white/30">
            <RefreshCw size={18} className="animate-spin mr-2" />
            Cargando artículos...
          </div>
        ) : posts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-white/30">
            <p className="text-lg font-medium">No hay artículos publicados aún</p>
            <p className="text-sm mt-1">Vuelve pronto — estamos trabajando en contenido nuevo.</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {posts.map((post) => (
                <PostCard key={post.post_id} post={post} />
              ))}
            </div>

            {/* Pagination */}
            {total > LIMIT && (
              <div className="flex items-center justify-center gap-3 mt-10">
                <button
                  onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                  disabled={offset === 0}
                  className="px-4 py-2 rounded-lg bg-white/5 border border-white/8 text-sm text-white/60 hover:text-white hover:bg-white/10 transition disabled:opacity-30"
                >
                  Anterior
                </button>
                <span className="text-xs text-white/30">
                  {offset + 1}–{Math.min(offset + LIMIT, total)} de {total}
                </span>
                <button
                  onClick={() => setOffset(offset + LIMIT)}
                  disabled={offset + LIMIT >= total}
                  className="px-4 py-2 rounded-lg bg-white/5 border border-white/8 text-sm text-white/60 hover:text-white hover:bg-white/10 transition disabled:opacity-30"
                >
                  Siguiente
                </button>
              </div>
            )}
          </>
        )}
      </main>

      {/* CTA */}
      <section className="border-t border-white/8 bg-[#0d0d0f]">
        <div className="max-w-3xl mx-auto px-6 py-14 text-center">
          <h2 className="text-2xl font-bold mb-3">¿Listo para empezar?</h2>
          <p className="text-white/50 mb-6">
            Hosting WordPress gestionado con backups automáticos, SSL y soporte 24/7.
          </p>
          <Link
            to="/"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-[#00ff88] text-black font-bold text-sm hover:bg-[#00e67a] transition"
          >
            Explorar planes <ArrowRight size={15} />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/8">
        <div className="max-w-6xl mx-auto px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-white/30">
          <span>© {new Date().getFullYear()} HostingGuard</span>
          <div className="flex gap-4">
            <Link to="/privacy" className="hover:text-white transition">Privacidad</Link>
            <Link to="/terms" className="hover:text-white transition">Términos</Link>
            <Link to="/blog" className="hover:text-white transition">Blog</Link>
          </div>
        </div>
      </footer>

    </div>
  );
}
