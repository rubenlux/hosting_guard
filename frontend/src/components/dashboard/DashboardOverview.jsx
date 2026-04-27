import { useState, useMemo, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Eye, FolderOpen, Download, Copy, RefreshCw,
  ExternalLink, Shield, Cpu, Globe, AlertTriangle,
  CheckCircle2, ChevronDown, ChevronRight, Search,
  Zap, Bot, CreditCard, Activity,
} from 'lucide-react';
import { getPixelDashboardSummary, getPixelTimeseries, getPixelRealtime } from '../../api/analytics';
import api from '../../services/api';

// ── Design tokens (V1 Linear/Vercel) ─────────────────────────────────────────
const T = {
  bg:         '#0a0a0a',
  surface:    '#0e0e0e',
  surface2:   '#131313',
  border:     '#1f1f1f',
  borderHi:   '#2a2a2a',
  text:       '#fafafa',
  textDim:    '#a1a1a1',
  textMute:   '#555',
  accent:     '#ff5f1f',
  accentSoft: 'rgba(255,95,31,0.10)',
  good:       '#10b981',
  goodSoft:   'rgba(16,185,129,0.10)',
  warn:       '#f59e0b',
  bad:        '#ef4444',
  badSoft:    'rgba(239,68,68,0.10)',
  violet:     '#8b5cf6',
  mono:       "'JetBrains Mono','Fira Code',ui-monospace,monospace",
};

// ── Utilities ─────────────────────────────────────────────────────────────────
function genSeries(seed, n, base, amp) {
  const out = []; let s = seed;
  for (let i = 0; i < n; i++) {
    s = (s * 9301 + 49297) % 233280;
    out.push(base + (s / 233280 - 0.5) * amp);
  }
  return out;
}

function relTime(iso) {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (d < 1)  return 'Ahora mismo';
  if (d < 60) return `Hace ${d} min`;
  const h = Math.floor(d / 60);
  if (h < 24) return `Hace ${h}h`;
  return `Hace ${Math.floor(h / 24)}d`;
}

// ── Sparkline ─────────────────────────────────────────────────────────────────
function Sparkline({ data, width = 80, height = 24, color = T.accent, fill = false, strokeWidth = 1.5 }) {
  if (!data || data.length < 2) return <div style={{ width, height }} />;
  const min = Math.min(...data), max = Math.max(...data), range = max - min || 1;
  const sx = width / (data.length - 1);
  const pts = data.map((v, i) => [i * sx, height - ((v - min) / range) * (height - 2) - 1]);
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  return (
    <svg width={width} height={height} style={{ display: 'block', flexShrink: 0 }}>
      {fill && <path d={`${path} L${width},${height} L0,${height} Z`} fill={color} fillOpacity="0.12" />}
      <path d={path} fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── Big area chart (Analytics section) ───────────────────────────────────────
function AreaChart({ series1, series2, width = 520, height = 140 }) {
  const pad = 8;
  const s1 = series1?.length > 1 ? series1 : genSeries(7, 30, 50, 30);
  const s2 = series2?.length > 1 ? series2 : genSeries(13, 30, 35, 20);
  const all = [...s1, ...s2];
  const min = 0, max = Math.max(...all, 1);
  const stepX = (width - pad * 2) / (s1.length - 1);
  const toY = v => height - pad - ((v - min) / (max - min)) * (height - pad * 2);
  const line = arr => arr.map((v, i) => `${i === 0 ? 'M' : 'L'}${(pad + i * stepX).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
  const area = arr => `${line(arr)} L${width - pad},${height - pad} L${pad},${height - pad} Z`;
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="ov-ga" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={T.accent} stopOpacity="0.35" />
          <stop offset="1" stopColor={T.accent} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="ov-gb" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={T.violet} stopOpacity="0.22" />
          <stop offset="1" stopColor={T.violet} stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 25, 50, 75, 100].map((y, i) => {
        const cy = toY((y / 100) * max);
        return <line key={i} x1={pad} x2={width - pad} y1={cy} y2={cy} stroke={T.border} strokeDasharray="2 4" />;
      })}
      <path d={area(s1)} fill="url(#ov-ga)" />
      <path d={line(s1)} fill="none" stroke={T.accent} strokeWidth="1.6" />
      <path d={area(s2)} fill="url(#ov-gb)" />
      <path d={line(s2)} fill="none" stroke={T.violet} strokeWidth="1.6" />
    </svg>
  );
}

// ── Visitor dot-grid world map ────────────────────────────────────────────────
function VisitorMap({ liveCount = 0 }) {
  const dots = useMemo(() => {
    const result = [];
    for (let y = 0; y < 20; y++) for (let x = 0; x < 58; x++) {
      const lon = x / 58, lat = y / 20;
      const land = (
        (lon > 0.06 && lon < 0.30 && lat > 0.18 && lat < 0.55 && lon + lat * 0.5 > 0.20) ||
        (lon > 0.32 && lon < 0.45 && lat > 0.25 && lat < 0.85) ||
        (lon > 0.46 && lon < 0.62 && lat > 0.18 && lat < 0.50) ||
        (lon > 0.62 && lon < 0.85 && lat > 0.20 && lat < 0.55) ||
        (lon > 0.85 && lon < 0.95 && lat > 0.55 && lat < 0.80)
      );
      if (land) result.push([x * 5.5 + 4, y * 5.5 + 4]);
    }
    return result;
  }, []);
  return (
    <div style={{ position: 'relative', width: '100%', height: 90, overflow: 'hidden' }}>
      <svg width="100%" height="90" viewBox="0 0 320 90" preserveAspectRatio="xMidYMid slice">
        {dots.map(([cx, cy], i) => <circle key={i} cx={cx} cy={cy} r="1" fill={T.borderHi} />)}
        {liveCount > 0 && (
          <g transform="translate(100,58)">
            <circle r="14" fill={T.accent} fillOpacity="0.10">
              <animate attributeName="r" values="5;16;5" dur="2.5s" repeatCount="indefinite" />
              <animate attributeName="fill-opacity" values="0.25;0;0.25" dur="2.5s" repeatCount="indefinite" />
            </circle>
            <circle r="3" fill={T.accent} />
          </g>
        )}
      </svg>
      {liveCount > 0 && (
        <div style={{ position: 'absolute', bottom: 5, left: 10, fontSize: 10, color: T.textMute, fontFamily: T.mono, display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ width: 5, height: 5, borderRadius: 999, background: T.accent, display: 'inline-block' }} />
          {liveCount} visitante{liveCount !== 1 ? 's' : ''} activo{liveCount !== 1 ? 's' : ''} · LATAM
        </div>
      )}
    </div>
  );
}

// ── Pulse dot ────────────────────────────────────────────────────────────────
function PulseDot({ color = T.good, size = 7 }) {
  return (
    <span style={{ position: 'relative', display: 'inline-flex', width: size, height: size, flexShrink: 0 }}>
      <span style={{ position: 'absolute', inset: 0, borderRadius: 999, background: color, animation: 'ov-pulse 2s infinite' }} />
      <span style={{ position: 'absolute', inset: 1.5, borderRadius: 999, background: color }} />
    </span>
  );
}

// ── KPI stat card ─────────────────────────────────────────────────────────────
function StatCard({ label, value, suffix, foot, series, color, IconC, alert }) {
  return (
    <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px', flex: 1, minWidth: 0, overflow: 'hidden', position: 'relative' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ fontSize: 10, color: T.textMute, letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 600 }}>{label}</div>
        <div style={{ width: 22, height: 22, borderRadius: 5, background: alert ? T.badSoft : T.surface2, border: `1px solid ${T.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          {IconC && <IconC size={12} style={{ color: alert ? T.bad : T.textMute }} />}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 3, marginBottom: 8 }}>
        <span style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-0.035em', color: alert ? T.bad : T.text, lineHeight: 1 }}>{value}</span>
        {suffix && <span style={{ fontSize: 14, color: T.textMute, fontFamily: T.mono }}>{suffix}</span>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 11, color: T.textDim }}>{foot}</div>
        {series && <Sparkline data={series} width={72} height={22} color={color} fill strokeWidth={1.3} />}
      </div>
    </div>
  );
}

// ── Section card wrapper ──────────────────────────────────────────────────────
function Card({ title, sub, right, children, padless, style }) {
  return (
    <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10, ...style }}>
      {(title || right) && (
        <div style={{ padding: '12px 14px 10px', display: 'flex', alignItems: 'center', borderBottom: `1px solid ${T.border}` }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {title && <div style={{ fontSize: 13, fontWeight: 600, color: T.text, letterSpacing: '-0.01em' }}>{title}</div>}
            {sub && <div style={{ fontSize: 10.5, color: T.textMute, marginTop: 2, fontFamily: T.mono }}>{sub}</div>}
          </div>
          {right && <div style={{ flexShrink: 0 }}>{right}</div>}
        </div>
      )}
      <div style={{ padding: padless ? 0 : 14 }}>{children}</div>
    </div>
  );
}

// ── Icon button ───────────────────────────────────────────────────────────────
const iconBtn = {
  background: 'transparent', color: T.textDim,
  border: `1px solid ${T.border}`, width: 26, height: 26, borderRadius: 5,
  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
  padding: 0,
};

// ── Site row ──────────────────────────────────────────────────────────────────
function SiteRow({ hosting, healthData, healthHistory, onOpenLogs, onOpenFiles, onUpload, onRestart }) {
  const [hover, setHover] = useState(false);
  const hd = healthData?.[hosting.hosting_id] ?? {};
  const score = hd.score ?? hosting.health ?? 100;
  const cpu   = parseFloat(hd.cpu ?? hosting.cpu ?? 0);
  const ram   = parseFloat(hd.ram ?? hosting.ram ?? 0);
  const hist  = healthHistory?.[hosting.hosting_id] ?? [];
  const series = hist.length > 2 ? hist.map(h => h.score ?? 100) : genSeries((hosting.hosting_id || 1) * 17, 24, ram, 2);
  const scoreColor = score >= 90 ? T.good : score >= 60 ? T.warn : T.bad;
  const letter = hosting.name?.[0]?.toUpperCase() ?? '?';
  const domain = hosting.subdomain ? `${hosting.subdomain}.hostingguard.lat` : hosting.name;
  const siteUrl = `https://${domain}`;

  return (
    <div
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 8, background: hover ? T.surface2 : 'transparent', border: `1px solid ${hover ? T.borderHi : 'transparent'}`, transition: 'background .12s, border-color .12s' }}
    >
      {/* Avatar */}
      <div style={{ width: 32, height: 32, borderRadius: 7, background: `linear-gradient(135deg, ${T.accent} 0%, #f59e0b 100%)`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, color: '#fff', flexShrink: 0 }}>
        {letter}
      </div>

      {/* Name + domain */}
      <div style={{ minWidth: 0, width: 190, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: T.text, letterSpacing: '-0.01em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{hosting.name}</span>
          <span style={{ width: 5, height: 5, borderRadius: 999, background: hosting.status === 'active' ? T.good : T.bad, boxShadow: hosting.status === 'active' ? `0 0 6px ${T.good}` : 'none', flexShrink: 0 }} />
        </div>
        <div style={{ fontSize: 10.5, color: T.textMute, fontFamily: T.mono, marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{domain}</div>
      </div>

      {/* Metrics */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flex: 1 }}>
        <div>
          <div style={{ fontSize: 9, color: T.textMute, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 2 }}>CPU</div>
          <div style={{ fontSize: 12, color: T.text, fontFamily: T.mono, fontWeight: 500 }}>{cpu.toFixed(2)}%</div>
        </div>
        <div>
          <div style={{ fontSize: 9, color: T.textMute, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 2 }}>RAM</div>
          <div style={{ fontSize: 12, color: T.text, fontFamily: T.mono, fontWeight: 500 }}>{ram.toFixed(1)}%</div>
        </div>
        <div>
          <div style={{ fontSize: 9, color: T.textMute, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 2 }}>SALUD</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 48, height: 3, borderRadius: 999, background: T.border, overflow: 'hidden' }}>
              <div style={{ width: `${score}%`, height: '100%', background: scoreColor, transition: 'width .4s' }} />
            </div>
            <span style={{ fontSize: 11, color: scoreColor, fontFamily: T.mono, fontWeight: 600 }}>{score}</span>
          </div>
        </div>
        <Sparkline data={series} width={80} height={22} color={scoreColor} fill strokeWidth={1.3} />
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, opacity: hover ? 1 : 0.45, transition: 'opacity .12s', flexShrink: 0 }}>
        <button style={iconBtn} title="Logs" onClick={() => onOpenLogs?.(hosting)}><Eye size={12} /></button>
        <button style={iconBtn} title="Archivos" onClick={() => onOpenFiles?.(hosting)}><FolderOpen size={12} /></button>
        <button style={iconBtn} title="Subir archivo" onClick={() => onUpload?.(hosting)}><Download size={12} /></button>
        <button style={iconBtn} title="Copiar dominio" onClick={() => navigator.clipboard.writeText(domain)}><Copy size={12} /></button>
        <button style={iconBtn} title="Reiniciar" onClick={() => onRestart?.(hosting.hosting_id)}><RefreshCw size={12} /></button>
        <a
          href={siteUrl} target="_blank" rel="noopener noreferrer"
          style={{ background: T.text, color: '#000', border: 'none', padding: '4px 10px', borderRadius: 5, fontSize: 11.5, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, textDecoration: 'none', whiteSpace: 'nowrap' }}
        >
          Abrir <ExternalLink size={10} />
        </a>
      </div>
    </div>
  );
}

// ── Activity feed ─────────────────────────────────────────────────────────────
function ActivityFeedV1({ events }) {
  const rows = events.slice(0, 6);
  return (
    <div>
      {rows.length === 0 ? (
        <div style={{ padding: '20px 14px', fontSize: 12, color: T.textMute, textAlign: 'center' }}>Sin actividad reciente</div>
      ) : rows.map((ev, i) => {
        const type = (ev.event_type ?? '').toUpperCase();
        const site = ev.site_name ?? ev.source ?? '—';
        const score = ev.score ?? ev.health_score ?? 100;
        const cpu  = parseFloat(ev.cpu_pct ?? ev.cpu ?? 0);
        const ram  = parseFloat(ev.ram_pct ?? ev.ram ?? 0);
        const isFirst = i === 0;
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 14px', borderBottom: i < rows.length - 1 ? `1px solid ${T.border}` : 'none' }}>
            <span style={{ marginTop: 5, flexShrink: 0 }}>
              <PulseDot color={score >= 90 ? T.good : T.warn} size={6} />
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 10, color: T.textMute, fontFamily: T.mono, letterSpacing: '0.05em' }}>{type || 'EVENT'}</span>
                <span style={{ fontSize: 11.5, color: T.text, fontWeight: 500 }}>{site}</span>
                <span style={{ marginLeft: 'auto', fontSize: 10, color: T.textMute, fontFamily: T.mono, whiteSpace: 'nowrap' }}>
                  {ev.created_at ? relTime(ev.created_at) : ev.time ?? '—'}
                </span>
              </div>
              <div style={{ fontSize: 10.5, color: T.textDim, fontFamily: T.mono, marginTop: 3, display: 'flex', gap: 10 }}>
                <span>score=<span style={{ color: T.good }}>{score}</span></span>
                <span>cpu=<span style={{ color: T.text }}>{cpu.toFixed(2)}%</span></span>
                <span>ram=<span style={{ color: T.text }}>{ram.toFixed(2)}%</span></span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function DashboardOverview({
  hostings = [],
  healthData = {},
  healthHistory = {},
  alerts = [],
  events = [],
  advisories = [],
  avgHealthScore,
  avgCpu,
  unresolved = 0,
  user,
  onTopup,
  onRefresh,
  onOpenLogs,
  onOpenFiles,
  onUpload,
  onRestart,
  userActionLoading,
}) {
  const navigate = useNavigate();

  // Analytics: fetch pixel stats for primary site if available
  const [pixelSites, setPixelSites] = useState([]);
  const [pixelStats, setPixelStats] = useState(null);
  const [pixelTimeseries, setPixelTimeseries] = useState(null);
  const [pixelRealtime, setPixelRealtime] = useState(null);
  const [analyticsIdx, setAnalyticsIdx] = useState(0);

  useEffect(() => {
    api.get('/pixel/sites').then(r => setPixelSites(r.data ?? [])).catch(() => {});
  }, []);

  const activeSite = pixelSites[analyticsIdx] ?? null;

  useEffect(() => {
    if (!activeSite) return;
    const id = activeSite.site_id;
    Promise.all([
      getPixelDashboardSummary(id, 30).catch(() => null),
      getPixelTimeseries(id, 30).catch(() => null),
      getPixelRealtime(id).catch(() => null),
    ]).then(([stats, ts, rt]) => {
      setPixelStats(stats);
      setPixelTimeseries(ts);
      setPixelRealtime(rt);
    });
  }, [activeSite]);

  // Derived KPI sparkline series (deterministic, visual only)
  const seriesSites   = useMemo(() => genSeries(5,  30, 2,   0.2), []);
  const seriesHealth  = useMemo(() => genSeries(11, 30, 100, 0.5), []);
  const seriesCpu     = useMemo(() => genSeries(3,  30, 0.5, 1),   []);
  const seriesAlerts  = useMemo(() => genSeries(17, 30, 0.5, 0.8), []);

  // Analytics chart series from pixel timeseries data
  const chartViews = useMemo(() => {
    const pts = pixelTimeseries?.points ?? [];
    return pts.length > 2 ? pts.map(p => p.page_views ?? 0) : null;
  }, [pixelTimeseries]);
  const chartSessions = useMemo(() => {
    const pts = pixelTimeseries?.points ?? [];
    return pts.length > 2 ? pts.map(p => p.sessions ?? 0) : null;
  }, [pixelTimeseries]);

  const active = hostings.filter(h => h.status === 'active').length;
  const total  = hostings.length;
  const pct    = total > 0 ? Math.round((active / total) * 100) : 0;
  const health = avgHealthScore ?? 100;
  const cpu    = parseFloat(avgCpu ?? 0);
  const cpuColor = cpu > 85 ? T.bad : cpu > 60 ? T.warn : T.accent;

  const retention    = pixelStats?.retention_rate   ?? pixelStats?.bounce_rate != null ? Math.round((1 - pixelStats.bounce_rate / 100) * 100) : null;
  const liveUsers    = pixelRealtime?.active_now     ?? 0;
  const todayViews   = pixelStats?.page_views_today  ?? pixelStats?.total_page_views ?? 0;

  // Session bars (last 7 points from timeseries or fallback)
  const sessionBars = useMemo(() => {
    const pts = pixelTimeseries?.points ?? [];
    if (pts.length >= 7) return pts.slice(-7).map(p => p.sessions ?? 0);
    return [8, 14, 6, 22, 11, 19, 16];
  }, [pixelTimeseries]);
  const barMax = Math.max(...sessionBars, 1);

  const topAdvisory = advisories.find(a => a.requiresAttention) ?? advisories[0] ?? null;
  const allOk = advisories.every(a => !a.requiresAttention);

  return (
    <div style={{ padding: '18px 22px 32px', fontFamily: "'Inter', system-ui, sans-serif" }}>
      <style>{`
        @keyframes ov-pulse { 0%,100% { transform:scale(1);opacity:1; } 50% { transform:scale(1.5);opacity:0.4; } }
      `}</style>

      {/* ── Page header ────────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 5 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, letterSpacing: '-0.025em', color: T.text }}>Dashboard Overview</h1>
          <span style={{ fontSize: 9.5, color: T.textMute, fontFamily: T.mono, padding: '2px 8px', border: `1px solid ${T.border}`, borderRadius: 999, letterSpacing: '0.08em' }}>SISTEMA ACTIVO</span>
        </div>
        <div style={{ fontSize: 12.5, color: T.textDim, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 6, height: 6, borderRadius: 999, background: T.good, boxShadow: `0 0 6px ${T.good}`, display: 'inline-block' }} />
            Salud <span style={{ color: T.text, fontWeight: 600, fontFamily: T.mono }}>{health}/100</span>
          </span>
          <span style={{ color: T.border }}>·</span>
          <span>Todo operativo</span>
          <span style={{ color: T.border }}>·</span>
          <span>{active} sitio{active !== 1 ? 's' : ''} activo{active !== 1 ? 's' : ''}</span>
          {unresolved > 0 && <>
            <span style={{ color: T.border }}>·</span>
            <span style={{ color: T.accent }}>{unresolved} alerta{unresolved !== 1 ? 's' : ''} sin resolver</span>
          </>}
        </div>
      </div>

      {/* ── KPI cards ──────────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 14 }}>
        <StatCard
          label="Sitios Activos" value={active} suffix={`/${total}`}
          foot={<span style={{ color: T.good }}>● {pct}% operativos</span>}
          series={seriesSites} color={T.good} IconC={Globe}
        />
        <StatCard
          label="Salud General" value={health} suffix="/100"
          foot={<span>↑ Estable últimas 24h</span>}
          series={seriesHealth} color={T.violet} IconC={Shield}
        />
        <StatCard
          label="CPU Promedio" value={avgCpu ?? '0.0'} suffix="%"
          foot={<span style={{ color: cpuColor }}>{cpu > 85 ? 'Carga alta' : cpu > 60 ? 'Carga moderada' : 'Carga normal'}</span>}
          series={seriesCpu} color={cpuColor} IconC={Cpu}
        />
        <StatCard
          label="Alertas Activas" value={unresolved}
          foot={unresolved > 0
            ? <span style={{ color: T.accent }}>{unresolved} sin resolver{alerts[0]?.source ? ` · ${alerts[0].source}` : ''}</span>
            : <span style={{ color: T.good }}>Sin alertas activas</span>}
          series={seriesAlerts} color={unresolved > 0 ? T.bad : T.good} IconC={AlertTriangle} alert={unresolved > 0}
        />
      </div>

      {/* ── Sites + right rail ─────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 12, marginBottom: 14 }}>
        {/* Sites card */}
        <Card
          title="Sus Proyectos"
          sub={`${total} sitio${total !== 1 ? 's' : ''} · sincronizado hace 2 min`}
          right={
            <div style={{ display: 'flex', gap: 6 }}>
              <button style={{ ...iconBtn, width: 28, height: 28 }} onClick={onRefresh}><RefreshCw size={12} /></button>
              <button onClick={() => navigate('/sites')} style={{ background: T.surface2, color: T.text, border: `1px solid ${T.border}`, padding: '4px 10px', borderRadius: 5, fontSize: 11.5, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                Ver todos
              </button>
            </div>
          }
          padless
        >
          <div style={{ padding: '6px 6px' }}>
            {hostings.length === 0 ? (
              <div style={{ padding: '24px 14px', textAlign: 'center', fontSize: 12, color: T.textMute }}>No hay sitios todavía</div>
            ) : hostings.map(h => (
              <SiteRow
                key={h.hosting_id} hosting={h}
                healthData={healthData} healthHistory={healthHistory}
                onOpenLogs={onOpenLogs} onOpenFiles={onOpenFiles}
                onUpload={onUpload} onRestart={onRestart}
              />
            ))}
          </div>
        </Card>

        {/* Right rail */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* AI Advisory */}
          <Card
            title="AI Advisory"
            right={
              <span style={{ fontSize: 9.5, color: allOk ? T.good : T.warn, fontFamily: T.mono, letterSpacing: '0.1em', padding: '3px 8px', background: allOk ? T.goodSoft : 'rgba(245,158,11,0.10)', borderRadius: 999 }}>
                ● {allOk ? 'TODO OK' : 'REVISAR'}
              </span>
            }
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
              <div style={{ width: 32, height: 32, borderRadius: 8, background: allOk ? T.goodSoft : T.accentSoft, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {allOk
                  ? <CheckCircle2 size={16} style={{ color: T.good }} />
                  : <Zap size={16} style={{ color: T.accent }} />}
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 3 }}>
                  {allOk ? 'Sistema estable' : (topAdvisory?.title ?? 'Atención requerida')}
                </div>
                <div style={{ fontSize: 11.5, color: T.textDim, lineHeight: 1.45 }}>
                  {allOk
                    ? 'Todos los hostings operando con normalidad.'
                    : (topAdvisory?.message ?? 'Revisá el panel de Advisory.')}
                </div>
              </div>
            </div>
            {!allOk && (
              <button onClick={() => navigate('/advisory')} style={{ marginTop: 10, width: '100%', background: T.surface2, color: T.text, border: `1px solid ${T.border}`, padding: '6px 12px', borderRadius: 6, fontSize: 11.5, cursor: 'pointer', textAlign: 'center' }}>
                Ver Advisory →
              </button>
            )}
          </Card>

          {/* Account */}
          <Card
            title="Tu Cuenta"
            right={
              user?.card_last_four
                ? <span style={{ fontSize: 10, color: T.textDim, fontFamily: T.mono }}>•••• {user.card_last_four}</span>
                : <span style={{ fontSize: 10, color: T.bad, fontFamily: T.mono }}>● Sin tarjeta</span>
            }
          >
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 4 }}>
              <span style={{ fontSize: 11, color: T.textMute }}>Saldo</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12 }}>
              <span style={{ fontSize: 32, fontWeight: 700, letterSpacing: '-0.035em', color: T.text, lineHeight: 1 }}>
                ${parseFloat(user?.balance ?? 0).toFixed(2)}
              </span>
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', background: T.accentSoft, color: T.accent, borderRadius: 4, letterSpacing: '0.08em' }}>
                {(user?.plan ?? 'FREE').toUpperCase()}
              </span>
            </div>
            <button
              onClick={onTopup} disabled={userActionLoading}
              style={{ width: '100%', background: T.accent, color: '#000', border: 'none', padding: '8px 12px', borderRadius: 6, fontSize: 12.5, fontWeight: 700, cursor: 'pointer', marginBottom: 8, opacity: userActionLoading ? 0.6 : 1 }}
            >
              Recargar +$10
            </button>
            <div style={{ textAlign: 'center', fontSize: 11, color: T.textMute, cursor: 'pointer' }} onClick={() => navigate('/dashboard')}>
              Ver facturación →
            </div>
          </Card>
        </div>
      </div>

      {/* ── Analytics + Activity ───────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 330px', gap: 12 }}>
        {/* Analytics */}
        <Card
          title="Analytics"
          sub={activeSite ? `${activeSite.name} · vistas y sesiones únicas` : 'Sin sitios de analytics registrados'}
          right={
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {pixelSites.length > 1 && (
                <div style={{ position: 'relative' }}>
                  <select
                    value={analyticsIdx}
                    onChange={e => setAnalyticsIdx(Number(e.target.value))}
                    style={{ appearance: 'none', background: T.surface2, color: T.text, border: `1px solid ${T.border}`, padding: '4px 24px 4px 8px', borderRadius: 5, fontSize: 11, cursor: 'pointer' }}
                  >
                    {pixelSites.map((s, i) => <option key={s.site_id} value={i}>{s.name}</option>)}
                  </select>
                  <ChevronDown size={12} style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)', color: T.textMute, pointerEvents: 'none' }} />
                </div>
              )}
              {pixelSites.length === 1 && (
                <div style={{ fontSize: 12, color: T.textDim, fontWeight: 500 }}>{pixelSites[0]?.name}</div>
              )}
              <button onClick={() => navigate('/pixel')} style={{ background: T.surface2, color: T.text, border: `1px solid ${T.border}`, padding: '4px 10px', borderRadius: 5, fontSize: 11.5, cursor: 'pointer' }}>Ver todo</button>
            </div>
          }
        >
          {!activeSite ? (
            <div style={{ padding: '24px', textAlign: 'center', fontSize: 12, color: T.textMute }}>
              Registrá un pixel en <span onClick={() => navigate('/pixel')} style={{ color: T.accent, cursor: 'pointer' }}>Pixel Analytics</span> para ver datos de tráfico aquí.
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px 110px', gap: 14 }}>
              {/* Chart */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div>
                    <div style={{ fontSize: 12, color: T.textDim, fontWeight: 500 }}>Tráfico del sitio</div>
                    <div style={{ fontSize: 10, color: T.textMute, fontFamily: T.mono, marginTop: 1 }}>últimos 30 días</div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 10.5, color: T.textDim }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ width: 8, height: 2, background: T.accent, display: 'inline-block' }} /> Vistas
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ width: 8, height: 2, background: T.violet, display: 'inline-block' }} /> Sesiones
                    </span>
                  </div>
                </div>
                <AreaChart series1={chartViews} series2={chartSessions} />
              </div>

              {/* Retention */}
              <div style={{ borderLeft: `1px solid ${T.border}`, paddingLeft: 14 }}>
                <div style={{ fontSize: 10, color: T.textMute, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>Retención</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: T.text, letterSpacing: '-0.03em', lineHeight: 1 }}>
                  {retention != null ? retention : pixelStats?.sessions ?? '—'}
                  {retention != null && <span style={{ fontSize: 14, color: T.textMute }}>%</span>}
                </div>
                {retention != null && (
                  <div style={{ marginTop: 5, fontSize: 10.5, color: T.warn, display: 'flex', alignItems: 'center' }}>
                    <span style={{ padding: '2px 6px', background: 'rgba(245,158,11,0.1)', borderRadius: 3, fontFamily: T.mono }}>
                      ● {retention >= 60 ? 'Buena' : retention >= 40 ? 'Regular' : 'Baja'}
                    </span>
                  </div>
                )}
                <div style={{ height: 1, background: T.border, margin: '10px 0' }} />
                <div style={{ fontSize: 10, color: T.textMute, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 5 }}>Sesiones / día</div>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 36 }}>
                  {sessionBars.map((v, i) => (
                    <div key={i} style={{ flex: 1, height: `${(v / barMax) * 100}%`, background: i === sessionBars.length - 1 ? T.accent : T.borderHi, borderRadius: '2px 2px 0 0', minHeight: 2 }} />
                  ))}
                </div>
              </div>

              {/* Live */}
              <div style={{ borderLeft: `1px solid ${T.border}`, paddingLeft: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <PulseDot color={T.good} size={7} />
                  <span style={{ fontSize: 10, color: T.good, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 600 }}>En vivo</span>
                </div>
                <div style={{ fontSize: 28, fontWeight: 700, color: T.text, letterSpacing: '-0.03em', lineHeight: 1 }}>{liveUsers}</div>
                <div style={{ fontSize: 10.5, color: T.textDim, marginTop: 4 }}>usuario{liveUsers !== 1 ? 's' : ''} activo{liveUsers !== 1 ? 's' : ''}</div>
                <div style={{ height: 1, background: T.border, margin: '10px 0' }} />
                <div style={{ fontSize: 10, color: T.textMute, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4 }}>Origen</div>
                <VisitorMap liveCount={liveUsers} />
              </div>
            </div>
          )}

          {/* Pages top strip */}
          {pixelStats?.top_pages?.length > 0 && (
            <div style={{ borderTop: `1px solid ${T.border}`, marginTop: 14, paddingTop: 10 }}>
              <div style={{ fontSize: 10, color: T.textMute, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>Páginas más visitadas</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                {pixelStats.top_pages.slice(0, 3).map((p, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 11, color: T.textDim, fontFamily: T.mono, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.url ?? p.page ?? '/'}</span>
                    <span style={{ fontSize: 10.5, color: T.textMute, fontFamily: T.mono, flexShrink: 0 }}>{p.views ?? p.count ?? 0}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>

        {/* Activity */}
        <Card
          title="Actividad Reciente"
          right={<span style={{ fontSize: 10.5, color: T.textDim, fontFamily: T.mono, padding: '3px 8px', border: `1px solid ${T.border}`, borderRadius: 999, cursor: 'pointer' }} onClick={onRefresh}>historial</span>}
          padless
        >
          <ActivityFeedV1 events={events} />
        </Card>
      </div>
    </div>
  );
}
