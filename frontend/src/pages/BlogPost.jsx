import React, { useEffect, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { ShieldCheck, ArrowLeft, Calendar, Tag, ArrowRight, RefreshCw } from 'lucide-react';
import { getBlogPost, listBlogPosts } from '../services/api';

function fmtDate(str) {
  if (!str) return '';
  return new Date(str).toLocaleDateString('es-AR', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

export default function BlogPost() {
  const { slug }      = useParams();
  const navigate      = useNavigate();
  const [post, setPost]         = useState(null);
  const [related, setRelated]   = useState([]);
  const [loading, setLoading]   = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotFound(false);

    getBlogPost(slug)
      .then((p) => {
        if (cancelled) return;
        setPost(p);
        // Load related (same category, exclude current)
        return listBlogPosts({ limit: 4, offset: 0 }).then((res) => {
          if (cancelled) return;
          const others = (res.posts || []).filter((r) => r.slug !== slug);
          setRelated(others.slice(0, 3));
        });
      })
      .catch((err) => {
        if (!cancelled) {
          if (err?.response?.status === 404) setNotFound(true);
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [slug]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#080809] flex items-center justify-center text-white/30">
        <RefreshCw size={18} className="animate-spin mr-2" /> Cargando...
      </div>
    );
  }

  if (notFound || !post) {
    return (
      <div className="min-h-screen bg-[#080809] flex flex-col items-center justify-center gap-4 text-white/50">
        <p className="text-xl font-bold">Artículo no encontrado</p>
        <Link to="/blog" className="text-[#00ff88] text-sm hover:underline">← Volver al blog</Link>
      </div>
    );
  }

  const seoTitle = post.seo_title || post.title;
  const seoDesc  = post.seo_description || post.excerpt;

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
            <Link to="/blog" className="text-white/50 hover:text-white transition">Blog</Link>
            <Link to="/login" className="text-white/50 hover:text-white transition">Acceder</Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      {post.cover_image_url && (
        <div className="w-full h-64 md:h-80 overflow-hidden bg-white/5">
          <img
            src={post.cover_image_url}
            alt={post.title}
            className="w-full h-full object-cover"
            onError={(e) => { e.target.parentElement.style.display = 'none'; }}
          />
        </div>
      )}

      {/* Article */}
      <main className="max-w-3xl mx-auto px-6 py-10">

        {/* Back */}
        <Link
          to="/blog"
          className="inline-flex items-center gap-1.5 text-xs text-white/40 hover:text-white transition mb-6"
        >
          <ArrowLeft size={13} /> Todos los artículos
        </Link>

        {/* Meta */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          {post.category && (
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-widest text-[#00ff88]/70">
              <Tag size={10} /> {post.category}
            </span>
          )}
          <span className="flex items-center gap-1 text-xs text-white/30">
            <Calendar size={11} /> {fmtDate(post.published_at)}
          </span>
        </div>

        <h1 className="text-3xl md:text-4xl font-black leading-tight mb-6">{post.title}</h1>

        {post.excerpt && (
          <p className="text-lg text-white/60 leading-relaxed mb-8 border-l-2 border-[#00ff88]/30 pl-4">
            {post.excerpt}
          </p>
        )}

        {/* Content */}
        <div
          className="prose-blog"
          dangerouslySetInnerHTML={{ __html: post.content }}
        />

        {/* Tags */}
        {post.tags && (
          <div className="flex flex-wrap gap-2 mt-10 pt-6 border-t border-white/8">
            {post.tags.split(',').map((t) => t.trim()).filter(Boolean).map((tag) => (
              <span
                key={tag}
                className="text-[11px] px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-white/50"
              >
                #{tag}
              </span>
            ))}
          </div>
        )}

      </main>

      {/* Related posts */}
      {related.length > 0 && (
        <section className="border-t border-white/8 bg-[#0d0d0f]">
          <div className="max-w-6xl mx-auto px-6 py-12">
            <h2 className="text-lg font-bold mb-6">Más artículos</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {related.map((r) => (
                <Link
                  key={r.post_id}
                  to={`/blog/${r.slug}`}
                  className="group flex flex-col gap-2 bg-[#111] border border-white/8 rounded-xl p-4 hover:border-white/20 transition"
                >
                  {r.category && (
                    <span className="text-[10px] font-semibold uppercase tracking-widest text-[#00ff88]/60">
                      {r.category}
                    </span>
                  )}
                  <p className="text-sm font-semibold leading-snug group-hover:text-[#00ff88] transition line-clamp-2">
                    {r.title}
                  </p>
                  <span className="text-[11px] text-white/30">{fmtDate(r.published_at)}</span>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="border-t border-white/8">
        <div className="max-w-3xl mx-auto px-6 py-14 text-center">
          <h2 className="text-2xl font-bold mb-3">¿Listo para empezar?</h2>
          <p className="text-white/50 mb-6">
            Hosting WordPress gestionado con backups automáticos, SSL y soporte 24/7.
          </p>
          <Link
            to="/"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-[#00ff88] text-black font-bold text-sm hover:bg-[#00e67a] transition"
          >
            Ver planes <ArrowRight size={15} />
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
