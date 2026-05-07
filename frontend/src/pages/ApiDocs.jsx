import { Code2, ArrowLeft, Lock, Zap, Globe, Mail } from 'lucide-react';
import { Link } from 'react-router-dom';

const CONTACT_EMAIL = 'api@hostingguard.lat';

const PLANNED_ENDPOINTS = [
  { method: 'POST', path: '/api/v1/hostings',          desc: 'Crear un nuevo hosting' },
  { method: 'GET',  path: '/api/v1/hostings',          desc: 'Listar todos tus hostings' },
  { method: 'GET',  path: '/api/v1/hostings/:id',      desc: 'Detalle de un hosting' },
  { method: 'POST', path: '/api/v1/hostings/:id/restart', desc: 'Reiniciar un hosting' },
  { method: 'GET',  path: '/api/v1/hostings/:id/metrics', desc: 'Métricas de CPU, RAM y tráfico' },
  { method: 'GET',  path: '/api/v1/hostings/:id/logs',   desc: 'Logs del contenedor' },
  { method: 'POST', path: '/api/v1/pixel/events',      desc: 'Registrar eventos de analytics' },
  { method: 'GET',  path: '/api/v1/pixel/:site_id/stats', desc: 'Estadísticas de un sitio' },
];

const METHOD_COLOR = {
  GET:    'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  POST:   'bg-blue-500/10   text-blue-400   border-blue-500/20',
  DELETE: 'bg-red-500/10    text-red-400    border-red-500/20',
  PATCH:  'bg-amber-500/10  text-amber-400  border-amber-500/20',
};

export default function ApiDocs() {
  return (
    <div className="min-h-screen bg-[#080809] text-white pt-20">
      {/* Header */}
      <div className="border-b border-white/8 bg-[#0d0d0f]">
        <div className="max-w-4xl mx-auto px-6 py-5 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <Code2 className="w-5 h-5 text-primary" />
            <span className="font-bold text-white">Hosting<span className="text-primary">Guard</span></span>
          </Link>
          <Link to="/" className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-white transition-colors">
            <ArrowLeft className="w-4 h-4" />
            Volver al inicio
          </Link>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-16">
        {/* Under construction banner */}
        <div className="flex flex-col items-center text-center mb-16">
          <div className="relative mb-8">
            <div className="w-20 h-20 rounded-3xl bg-primary/10 border border-primary/20 flex items-center justify-center mx-auto">
              <Code2 className="w-9 h-9 text-primary" />
            </div>
            <div className="absolute -top-1 -right-1 w-6 h-6 rounded-full bg-amber-500/20 border border-amber-500/30 flex items-center justify-center">
              <span className="text-amber-400 text-[10px] font-black">!</span>
            </div>
          </div>

          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-semibold mb-4">
            <Zap className="w-3.5 h-3.5" />
            En construcción
          </div>

          <h1 className="text-4xl font-black text-white mb-4">API Docs</h1>
          <p className="text-gray-400 text-base max-w-lg leading-relaxed">
            Estamos construyendo la documentación pública de la API de HostingGuard. Pronto podrás automatizar e integrar tu hosting programáticamente.
          </p>
        </div>

        {/* Features cards */}
        <div className="grid sm:grid-cols-3 gap-4 mb-16">
          {[
            { icon: Lock,  title: 'API Keys',   desc: 'Autenticación segura mediante tokens con permisos granulares.' },
            { icon: Zap,   title: 'REST + JSON', desc: 'Endpoints RESTful con respuestas JSON y errores estandarizados.' },
            { icon: Globe, title: 'Webhooks',    desc: 'Recibí notificaciones en tiempo real de eventos del sistema.' },
          ].map(({ icon: Icon, title, desc }) => (
            <div key={title} className="p-5 rounded-2xl bg-white/3 border border-white/8 text-center">
              <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center mx-auto mb-3">
                <Icon className="w-5 h-5 text-primary" />
              </div>
              <div className="text-sm font-bold text-white mb-1">{title}</div>
              <div className="text-xs text-gray-500 leading-relaxed">{desc}</div>
            </div>
          ))}
        </div>

        {/* Planned endpoints */}
        <div className="mb-16">
          <h2 className="text-base font-bold text-white mb-1">Endpoints planificados</h2>
          <p className="text-xs text-gray-500 mb-5">Vista previa de los endpoints disponibles en la v1 de la API.</p>

          <div className="rounded-2xl border border-white/8 overflow-hidden bg-[#0d0d0f]">
            {PLANNED_ENDPOINTS.map((ep, i) => (
              <div
                key={i}
                className="flex items-center gap-4 px-5 py-3.5 border-b border-white/5 last:border-0 hover:bg-white/3 transition-colors"
              >
                <span className={`px-2.5 py-0.5 rounded text-[10px] font-black border font-mono shrink-0 ${METHOD_COLOR[ep.method] || ''}`}>
                  {ep.method}
                </span>
                <code className="text-xs text-gray-300 font-mono flex-1 truncate">{ep.path}</code>
                <span className="text-xs text-gray-600 hidden sm:block shrink-0">{ep.desc}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Early access CTA */}
        <div className="p-6 rounded-2xl bg-primary/5 border border-primary/20 text-center">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center mx-auto mb-3">
            <Mail className="w-5 h-5 text-primary" />
          </div>
          <h3 className="text-base font-bold text-white mb-2">¿Querés acceso anticipado?</h3>
          <p className="text-sm text-gray-400 mb-4 max-w-sm mx-auto">
            Si necesitás acceso a la API antes del lanzamiento oficial, escribinos y te incluimos en el programa de acceso anticipado.
          </p>
          <a
            href={`mailto:${CONTACT_EMAIL}?subject=Solicitud de acceso anticipado a la API`}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-black text-sm font-bold hover:bg-primary/90 transition-colors"
          >
            <Mail className="w-4 h-4" />
            Solicitar acceso anticipado
          </a>
          <p className="text-xs text-gray-600 mt-3">{CONTACT_EMAIL}</p>
        </div>
      </div>
    </div>
  );
}
