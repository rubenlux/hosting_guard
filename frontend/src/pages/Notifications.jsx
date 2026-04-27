import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Bell, ArrowLeft, CheckCheck, Trash2, Check, ExternalLink,
  AlertTriangle, Info, CheckCircle2, Zap, Shield, CreditCard,
  Server, RefreshCw, Filter, Package, Globe,
} from 'lucide-react';
import {
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  archiveNotification,
} from '../services/api';

/* ── constants ───────────────────────────────────────────────────────────── */
const SEVERITY_CFG = {
  critical:        { color: 'text-red-400',    bg: 'bg-red-500/10 border-red-500/20',       dot: 'bg-red-400',    label: 'Crítico'   },
  security:        { color: 'text-amber-400',  bg: 'bg-amber-500/10 border-amber-500/20',   dot: 'bg-amber-400',  label: 'Seguridad' },
  warning:         { color: 'text-amber-400',  bg: 'bg-amber-500/10 border-amber-500/20',   dot: 'bg-amber-400',  label: 'Aviso'     },
  action_required: { color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/20', dot: 'bg-orange-400', label: 'Acción'    },
  success:         { color: 'text-[#00ff88]',  bg: 'bg-[#00ff88]/8 border-[#00ff88]/15',   dot: 'bg-[#00ff88]',  label: 'OK'        },
  billing:         { color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/20', dot: 'bg-purple-400', label: 'Billing'   },
  info:            { color: 'text-blue-400',   bg: 'bg-blue-500/10 border-blue-500/20',     dot: 'bg-blue-400',   label: 'Info'      },
};

const CAT_CFG = {
  security:    { icon: <Shield className="w-3.5 h-3.5" />,      label: 'Seguridad'    },
  billing:     { icon: <CreditCard className="w-3.5 h-3.5" />,  label: 'Facturación'  },
  hosting:     { icon: <Server className="w-3.5 h-3.5" />,      label: 'Hosting'      },
  performance: { icon: <Zap className="w-3.5 h-3.5" />,         label: 'Rendimiento'  },
  wordpress:   { icon: <Globe className="w-3.5 h-3.5" />,       label: 'WordPress'    },
  migration:   { icon: <Package className="w-3.5 h-3.5" />,     label: 'Migración'    },
  account:     { icon: <CheckCircle2 className="w-3.5 h-3.5" />,label: 'Cuenta'       },
  system:      { icon: <Info className="w-3.5 h-3.5" />,        label: 'Sistema'      },
};

const STATUS_TABS = [
  { key: 'all',    label: 'Todas'   },
  { key: 'unread', label: 'No leídas' },
  { key: 'read',   label: 'Leídas'  },
];

const CATEGORIES = ['all', 'security', 'hosting', 'wordpress', 'migration', 'performance', 'billing', 'account', 'system'];
const SEVERITIES = ['all', 'critical', 'warning', 'success', 'info'];

function sevCfg(sev) { return SEVERITY_CFG[sev] || SEVERITY_CFG.info; }
function catCfg(cat) { return CAT_CFG[cat] || { icon: <Info className="w-3.5 h-3.5" />, label: cat }; }

function timeAgo(isoStr) {
  const d = new Date(isoStr);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60)    return 'hace un momento';
  if (diff < 3600)  return `hace ${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)}h`;
  if (diff < 86400 * 7) return `hace ${Math.floor(diff / 86400)}d`;
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatFull(isoStr) {
  return new Date(isoStr).toLocaleString('es-AR', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

/* ── single notification card ────────────────────────────────────────────── */
function NotifCard({ item, onRead, onArchive }) {
  const [expanded, setExpanded] = useState(false);
  const cfg    = sevCfg(item.severity);
  const cat    = catCfg(item.category);
  const unread = item.status === 'unread';

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0, marginBottom: 0, overflow: 'hidden' }}
      transition={{ duration: 0.18 }}
      className={`group relative rounded-xl border transition-all cursor-pointer
        ${unread
          ? `${cfg.bg} hover:brightness-110`
          : 'bg-white/2 border-white/6 hover:bg-white/4'
        }`}
      onClick={() => setExpanded(v => !v)}
    >
      {/* unread bar */}
      {unread && (
        <div className={`absolute left-0 top-3 bottom-3 w-0.5 rounded-full ${cfg.dot}`} />
      )}

      <div className="px-4 py-3.5 pl-5">
        {/* top row */}
        <div className="flex items-start gap-3">
          {/* severity dot */}
          <div className={`mt-1 w-2 h-2 rounded-full shrink-0 ${unread ? cfg.dot : 'bg-white/15'}`} />

          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-3">
              <span className={`text-sm font-semibold leading-tight ${unread ? 'text-white' : 'text-white/50'}`}>
                {item.title}
              </span>
              <span className="text-[10px] text-white/30 shrink-0 mt-0.5 font-mono">{timeAgo(item.created_at)}</span>
            </div>

            <p className={`text-xs mt-1 leading-relaxed ${expanded ? '' : 'line-clamp-2'} ${unread ? 'text-white/60' : 'text-white/30'}`}>
              {item.message}
            </p>

            {/* badges row */}
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <span className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md border ${cfg.bg} ${cfg.color}`}>
                {cfg.label}
              </span>
              <span className="flex items-center gap-1 text-[10px] text-white/35 bg-white/4 border border-white/6 px-1.5 py-0.5 rounded-md">
                {cat.icon}
                {cat.label}
              </span>
              <span className="text-[10px] text-white/20 font-mono">{item.channel}</span>
              {item.action_url && (
                <a
                  href={item.action_url.startsWith('http') ? item.action_url : `https://app.hostingguard.lat${item.action_url}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={e => e.stopPropagation()}
                  className="flex items-center gap-0.5 text-[10px] text-blue-400/70 hover:text-blue-300 transition-colors ml-auto"
                >
                  Ver <ExternalLink className="w-2.5 h-2.5" />
                </a>
              )}
            </div>

            {/* expanded detail */}
            <AnimatePresence>
              {expanded && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.15 }}
                  className="overflow-hidden"
                >
                  <div className="mt-3 pt-3 border-t border-white/6 text-[10px] text-white/30 font-mono space-y-0.5">
                    <div>ID: {item.notification_id}</div>
                    <div>Recibida: {formatFull(item.created_at)}</div>
                    {item.read_at && <div>Leída: {formatFull(item.read_at)}</div>}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* action buttons */}
          <div className="flex flex-col gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e => e.stopPropagation()}>
            {unread && (
              <button
                onClick={() => onRead(item.notification_id)}
                className="w-6 h-6 rounded-md flex items-center justify-center bg-white/6 hover:bg-[#00ff88]/20 hover:text-[#00ff88] transition-colors text-white/40"
                title="Marcar como leída"
              >
                <Check className="w-3 h-3" />
              </button>
            )}
            <button
              onClick={() => onArchive(item.notification_id)}
              className="w-6 h-6 rounded-md flex items-center justify-center bg-white/6 hover:bg-red-500/20 hover:text-red-400 transition-colors text-white/30"
              title="Archivar"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

/* ── main page ───────────────────────────────────────────────────────────── */
export default function Notifications({ embedded = false }) {
  const navigate  = useNavigate();
  const [items,   setItems]    = useState([]);
  const [loading, setLoading]  = useState(true);
  const [status,  setStatus]   = useState('all');
  const [category,setCategory] = useState('all');
  const [severity,setSeverity] = useState('all');
  const [total,   setTotal]    = useState(0);
  const [offset,  setOffset]   = useState(0);
  const [hasMore, setHasMore]  = useState(false);
  const LIMIT = 30;

  const load = useCallback(async (reset = false) => {
    setLoading(true);
    try {
      const params = { limit: LIMIT, offset: reset ? 0 : offset };
      if (status   !== 'all') params.status   = status;
      if (category !== 'all') params.category = category;
      if (severity !== 'all') params.severity = severity;
      const data = await getNotifications(params);
      const newItems = (data.items || []).filter(n => n.status !== 'archived');
      if (reset) {
        setItems(newItems);
        setOffset(newItems.length);
      } else {
        setItems(prev => [...prev, ...newItems]);
        setOffset(prev => prev + newItems.length);
      }
      setTotal(data.total || data.unread || 0);
      setHasMore(newItems.length === LIMIT);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [status, category, severity, offset]);

  useEffect(() => {
    setOffset(0);
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, category, severity]);

  const handleRead = async (id) => {
    try {
      await markNotificationRead(id);
      setItems(prev => prev.map(n => n.notification_id === id ? { ...n, status: 'read', read_at: new Date().toISOString() } : n));
    } catch { /* ignore */ }
  };

  const handleArchive = async (id) => {
    try {
      await archiveNotification(id);
      setItems(prev => prev.filter(n => n.notification_id !== id));
    } catch { /* ignore */ }
  };

  const handleMarkAll = async () => {
    try {
      await markAllNotificationsRead();
      setItems(prev => prev.map(n => ({ ...n, status: 'read', read_at: n.read_at || new Date().toISOString() })));
    } catch { /* ignore */ }
  };

  const visible  = items.filter(n => n.status !== 'archived');
  const unreadCt = visible.filter(n => n.status === 'unread').length;

  return (
    <div className={embedded ? 'text-white' : 'min-h-screen bg-[#0d0d0f] text-white'}>
      {/* ── top bar — hidden when embedded in dashboard sidebar ── */}
      {!embedded && (
      <div className="sticky top-0 z-20 bg-[#0d0d0f]/90 backdrop-blur border-b border-white/6">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center gap-3">
          <button
            onClick={() => navigate('/dashboard')}
            className="w-8 h-8 flex items-center justify-center rounded-lg bg-white/4 border border-white/8 hover:bg-white/8 transition-colors"
          >
            <ArrowLeft className="w-4 h-4 text-white/60" />
          </button>
          <Bell className="w-4 h-4 text-white/40" />
          <span className="text-sm font-semibold text-white/80">Notificaciones</span>
          {unreadCt > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-400 font-medium border border-red-500/20">
              {unreadCt} no leída{unreadCt !== 1 && 's'}
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">
            {unreadCt > 0 && (
              <button
                onClick={handleMarkAll}
                className="flex items-center gap-1.5 text-[11px] text-white/40 hover:text-white/70 transition-colors px-2.5 py-1.5 rounded-lg bg-white/4 border border-white/8 hover:bg-white/8"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                Leer todo
              </button>
            )}
            <button
              onClick={() => load(true)}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-white/4 border border-white/8 hover:bg-white/8 transition-colors"
              title="Recargar"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-white/40 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>
      )}

      <div className={embedded ? 'px-0 py-0' : 'max-w-3xl mx-auto px-4 py-6'}>
        {/* ── embedded header ── */}
        {embedded && (
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2">
              <span className="text-[22px] font-black text-white">Notificaciones</span>
              {unreadCt > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-400 font-medium border border-red-500/20">
                  {unreadCt}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {unreadCt > 0 && (
                <button
                  onClick={handleMarkAll}
                  className="flex items-center gap-1.5 text-[11px] text-white/40 hover:text-white/70 transition-colors px-2.5 py-1.5 rounded-lg bg-white/4 border border-white/8 hover:bg-white/8"
                >
                  <CheckCheck className="w-3.5 h-3.5" />
                  Leer todo
                </button>
              )}
              <button
                onClick={() => load(true)}
                className="w-8 h-8 flex items-center justify-center rounded-lg bg-white/4 border border-white/8 hover:bg-white/8 transition-colors"
              >
                <RefreshCw className={`w-3.5 h-3.5 text-white/40 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
        )}

        {/* ── filter bar ── */}
        <div className="mb-5 space-y-3">
          {/* status tabs */}
          <div className="flex gap-1 bg-white/3 border border-white/8 rounded-xl p-1 w-fit">
            {STATUS_TABS.map(t => (
              <button
                key={t.key}
                onClick={() => setStatus(t.key)}
                className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                  status === t.key
                    ? 'bg-white/10 text-white'
                    : 'text-white/35 hover:text-white/60'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* category + severity */}
          <div className="flex items-center gap-2 flex-wrap">
            <Filter className="w-3.5 h-3.5 text-white/25 shrink-0" />
            <div className="flex gap-1 flex-wrap">
              {CATEGORIES.map(cat => (
                <button
                  key={cat}
                  onClick={() => setCategory(cat)}
                  className={`text-[10px] px-2 py-1 rounded-lg border transition-colors ${
                    category === cat
                      ? 'bg-white/10 border-white/20 text-white'
                      : 'border-white/6 text-white/30 hover:text-white/50 hover:border-white/12'
                  }`}
                >
                  {cat === 'all' ? 'Todas las categorías' : catCfg(cat).label}
                </button>
              ))}
            </div>
            <div className="w-px h-3 bg-white/10 mx-1 hidden sm:block" />
            <div className="flex gap-1 flex-wrap">
              {SEVERITIES.map(sev => {
                const s = SEVERITY_CFG[sev];
                return (
                  <button
                    key={sev}
                    onClick={() => setSeverity(sev)}
                    className={`text-[10px] px-2 py-1 rounded-lg border transition-colors ${
                      severity === sev
                        ? sev === 'all'
                          ? 'bg-white/10 border-white/20 text-white'
                          : `${s.bg} ${s.color} border-current/30`
                        : 'border-white/6 text-white/30 hover:text-white/50 hover:border-white/12'
                    }`}
                  >
                    {sev === 'all' ? 'Todas' : s?.label || sev}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* ── list ── */}
        <div className="space-y-2">
          {loading && visible.length === 0 ? (
            <div className="py-20 text-center">
              <RefreshCw className="w-6 h-6 text-white/15 mx-auto mb-3 animate-spin" />
              <div className="text-sm text-white/25">Cargando notificaciones...</div>
            </div>
          ) : visible.length === 0 ? (
            <div className="py-20 text-center">
              <Bell className="w-10 h-10 text-white/8 mx-auto mb-3" />
              <div className="text-sm font-medium text-white/30">Sin notificaciones</div>
              <div className="text-xs text-white/18 mt-1">
                {status !== 'all' || category !== 'all' || severity !== 'all'
                  ? 'Probá cambiando los filtros'
                  : 'Cuando llegue algo, aparecerá aquí'}
              </div>
            </div>
          ) : (
            <AnimatePresence initial={false}>
              {visible.map(item => (
                <NotifCard
                  key={item.notification_id}
                  item={item}
                  onRead={handleRead}
                  onArchive={handleArchive}
                />
              ))}
            </AnimatePresence>
          )}
        </div>

        {/* ── load more ── */}
        {hasMore && !loading && (
          <div className="mt-4 text-center">
            <button
              onClick={() => load(false)}
              className="text-xs text-white/35 hover:text-white/60 transition-colors px-4 py-2 rounded-lg bg-white/3 border border-white/8 hover:bg-white/6"
            >
              Cargar más
            </button>
          </div>
        )}

        {/* ── footer count ── */}
        {visible.length > 0 && (
          <div className="mt-6 text-center text-[10px] text-white/15 font-mono">
            {visible.length} notificacion{visible.length !== 1 ? 'es' : ''} mostradas
          </div>
        )}
      </div>
    </div>
  );
}
