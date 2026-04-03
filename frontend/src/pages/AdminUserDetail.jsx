import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, RefreshCw, User } from 'lucide-react';
import { getAdminUserFull, getAdminHostingsMetrics } from '../services/api';

const statusColor = {
  active:   'text-[#00ff88]',
  stopped:  'text-danger',
  expired:  'text-red-600',
  error:    'text-danger',
  starting: 'text-[#ffaa00]',
};

// Render a single metric cell — shows '—' when value is null/undefined
function Metric({ label, value, color = 'text-white' }) {
  const display = value !== null && value !== undefined ? value : '—';
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-[9px] font-mono uppercase tracking-widest text-muted">{label}</div>
      <div className={`text-xs font-black font-mono ${display === '—' ? 'text-white/20' : color}`}>{display}</div>
    </div>
  );
}

// Uptime bar: last 20 checks as coloured dots
function UptimeBar({ history }) {
  if (!history || history.length === 0) return <span className="text-[9px] text-muted italic">sin historial</span>;
  return (
    <div className="flex gap-0.5 items-center">
      {history.slice(0, 20).reverse().map((c, i) => (
        <div
          key={i}
          title={`${new Date(c.checked_at).toLocaleTimeString()} — ${c.is_up ? 'UP' : 'DOWN'} ${c.response_ms != null ? `(${c.response_ms}ms)` : ''}`}
          className={`w-2 h-3 rounded-sm ${c.is_up ? 'bg-[#00ff88]' : 'bg-danger'}`}
        />
      ))}
    </div>
  );
}

export default function AdminUserDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  // dockerMetrics: { [container_name]: { cpu, memory, mem_pct, net_io } }
  const [dockerMetrics, setDockerMetrics] = useState({});
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('hostings');

  const fetchData = async () => {
    setLoading(true);
    try {
      // Parallel: user detail + live docker stats for all containers
      const [res, allMetrics] = await Promise.all([
        getAdminUserFull(id),
        getAdminHostingsMetrics().catch(() => []),  // non-fatal if docker unavailable
      ]);
      setData(res);
      // Index by container_name for O(1) lookup
      const idx = {};
      for (const m of allMetrics) {
        if (m.container_name && m.docker) idx[m.container_name] = m.docker;
      }
      setDockerMetrics(idx);
    } catch (err) {
      console.error('Error fetching user detail:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-20">
        <RefreshCw className="w-6 h-6 animate-spin text-accent" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-10 text-center text-muted">
        <div className="text-sm">Usuario no encontrado.</div>
        <button onClick={() => navigate(-1)} className="mt-4 btn-dash btn-ghost-dash text-xs">← Volver</button>
      </div>
    );
  }

  const { user, hostings, activity, decision_events, execution_events, human_events } = data;

  const tabs = [
    { id: 'hostings',    label: `Hostings (${hostings.length})` },
    { id: 'activity',    label: `Actividad (${activity.length})` },
    { id: 'decisions',   label: `Decisiones IA (${decision_events.length})` },
    { id: 'executions',  label: `Ejecuciones (${execution_events.length})` },
    { id: 'human',       label: `Acciones Humanas (${human_events.length})` },
  ];

  return (
    <div className="flex flex-col gap-6">

      {/* Back + header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate(-1)} className="btn-dash btn-ghost-dash text-xs flex items-center gap-1">
          <ArrowLeft className="w-3.5 h-3.5" /> Volver
        </button>
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <User className="w-5 h-5 text-[#00aaff]" /> {user.email}
          </h2>
          <div className="text-xs text-muted font-mono">
            ID: {user.user_id} · Creado: {user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
          </div>
        </div>
        <button onClick={fetchData} className="ml-auto btn-dash btn-ghost-dash text-xs flex items-center gap-1">
          <RefreshCw className="w-3.5 h-3.5" /> Actualizar
        </button>
      </div>

      {/* Profile cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Plan',     val: user.plan || 'free',                  color: 'text-[#00aaff]' },
          { label: 'Saldo',    val: `$${(user.balance || 0).toFixed(2)}`, color: 'text-[#00ff88]' },
          { label: 'Rol',      val: user.role || 'user',                   color: user.role === 'admin' ? 'text-danger' : 'text-muted' },
          { label: 'Hostings', val: hostings.length,                       color: 'text-[#aa00ff]' },
        ].map((m, i) => (
          <div key={i} className="p-4 bg-[#050505] rounded-xl border border-white/10">
            <div className="text-[9px] font-mono tracking-widest uppercase text-muted mb-1">{m.label}</div>
            <div className={`text-xl font-black font-mono text-glow uppercase ${m.color}`}>{m.val}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/5 pb-1 overflow-x-auto">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`text-xs font-mono uppercase tracking-widest px-4 py-2 rounded-t-lg transition-all whitespace-nowrap ${
              activeTab === tab.id
                ? 'bg-accent/10 text-accent border-b-2 border-accent'
                : 'text-muted hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── HOSTINGS TAB ─────────────────────────────────────────── */}
      {activeTab === 'hostings' && (
        <div className="flex flex-col gap-4">
          {hostings.length === 0 ? (
            <div className="p-8 text-center text-muted text-sm italic card-dash">Sin hostings.</div>
          ) : (
            hostings.map(h => {
              const docker  = dockerMetrics[h.container_name] || {};
              const traffic = h.traffic_24h  || {};
              const hasDocker  = Object.keys(docker).length > 0;
              const hasTraffic = traffic.total_requests != null;

              return (
                <div key={h.hosting_id} className="card-dash p-4 flex flex-col gap-4">

                  {/* Hosting header row */}
                  <div className="flex items-center gap-3 flex-wrap">
                    <div className={`text-[9px] font-black font-mono w-2 h-2 rounded-full mt-0.5 shrink-0 ${statusColor[h.status] ? 'bg-current' : 'bg-muted'} ${statusColor[h.status] || ''}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-bold text-white">{h.name}</div>
                      <div className="text-[10px] font-mono text-muted truncate">{h.subdomain}</div>
                    </div>
                    <span className={`text-[9px] font-black uppercase px-2 py-0.5 rounded ${statusColor[h.status] || 'text-muted'} bg-white/5`}>
                      {h.status}
                    </span>
                    <span className="text-[9px] font-mono uppercase text-muted bg-white/5 px-2 py-0.5 rounded">
                      {h.plan}
                    </span>
                    <span className="text-[9px] font-mono text-muted">
                      {h.created_at ? new Date(h.created_at).toLocaleDateString() : '—'}
                    </span>
                  </div>

                  {/* Metrics grid */}
                  <div className="grid grid-cols-4 md:grid-cols-8 gap-3 p-3 bg-black/30 rounded-xl border border-white/5">

                    {/* Live docker stats */}
                    <Metric
                      label="CPU"
                      value={hasDocker ? docker.cpu : null}
                      color="text-[#00aaff]"
                    />
                    <Metric
                      label="RAM"
                      value={hasDocker ? docker.memory?.split('/')[0]?.trim() : null}
                      color="text-[#ffaa00]"
                    />
                    <Metric
                      label="RAM %"
                      value={hasDocker ? docker.mem_pct : null}
                      color="text-[#ffaa00]"
                    />
                    <Metric
                      label="Net I/O"
                      value={hasDocker ? docker.net_io : null}
                      color="text-[#aa00ff]"
                    />

                    {/* Traffic 24h */}
                    <Metric
                      label="Requests 24h"
                      value={hasTraffic ? traffic.total_requests : null}
                      color="text-white"
                    />
                    <Metric
                      label="Err 4xx"
                      value={hasTraffic ? traffic.errors_4xx : null}
                      color={traffic.errors_4xx > 0 ? 'text-[#ffaa00]' : 'text-muted'}
                    />
                    <Metric
                      label="Err 5xx"
                      value={hasTraffic ? traffic.errors_5xx : null}
                      color={traffic.errors_5xx > 0 ? 'text-danger' : 'text-muted'}
                    />

                    {/* Uptime + response time */}
                    <Metric
                      label="Uptime 24h"
                      value={h.uptime_pct != null ? `${h.uptime_pct}%` : null}
                      color={
                        h.uptime_pct == null ? 'text-muted'
                        : h.uptime_pct >= 99  ? 'text-[#00ff88]'
                        : h.uptime_pct >= 90  ? 'text-[#ffaa00]'
                        : 'text-danger'
                      }
                    />
                  </div>

                  {/* Response time + uptime bar */}
                  <div className="flex items-center gap-6 flex-wrap">
                    <div className="flex flex-col gap-0.5">
                      <div className="text-[9px] font-mono uppercase tracking-widest text-muted">Resp. Avg</div>
                      <div className={`text-xs font-black font-mono ${h.avg_response_ms != null ? 'text-white' : 'text-white/20'}`}>
                        {h.avg_response_ms != null ? `${h.avg_response_ms} ms` : '—'}
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      <div className="text-[9px] font-mono uppercase tracking-widest text-muted">Historial uptime</div>
                      <UptimeBar history={h.uptime_history} />
                    </div>
                  </div>

                </div>
              );
            })
          )}
        </div>
      )}

      {/* ── ACTIVITY TAB ─────────────────────────────────────────── */}
      {activeTab === 'activity' && (
        <div className="card-dash overflow-x-auto">
          {activity.length === 0 ? (
            <div className="p-8 text-center text-muted text-sm italic">Sin actividad.</div>
          ) : (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-white/5 text-muted">
                  {['Contenedor', 'Tipo', 'Mensaje', 'Fecha'].map(h => (
                    <th key={h} className="text-left p-3 text-[9px] uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {activity.map((e, i) => (
                  <tr key={i} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                    <td className="p-3 text-[#00aaff]">{e.container_name}</td>
                    <td className="p-3 text-white uppercase">{e.event_type}</td>
                    <td className="p-3 text-muted">{e.message}</td>
                    <td className="p-3 text-muted">{e.created_at ? new Date(e.created_at).toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── DECISIONS TAB ────────────────────────────────────────── */}
      {activeTab === 'decisions' && (
        <div className="card-dash overflow-x-auto">
          {decision_events.length === 0 ? (
            <div className="p-8 text-center text-muted text-sm italic">Sin eventos de decisión IA.</div>
          ) : (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-white/5 text-muted">
                  {['ID', 'Estado', 'Confianza', 'Atención Humana', 'Timestamp'].map(h => (
                    <th key={h} className="text-left p-3 text-[9px] uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {decision_events.map(e => (
                  <tr key={e.event_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                    <td className="p-3 text-muted">{e.event_id.slice(0, 8)}</td>
                    <td className="p-3 text-white">{e.overall_status}</td>
                    <td className="p-3 text-[#00ff88]">{e.confidence_level}</td>
                    <td className="p-3">{e.requires_human_attention
                      ? <span className="text-danger">Sí</span>
                      : <span className="text-muted">No</span>}
                    </td>
                    <td className="p-3 text-muted">{e.timestamp ? new Date(e.timestamp).toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── EXECUTIONS TAB ───────────────────────────────────────── */}
      {activeTab === 'executions' && (
        <div className="card-dash overflow-x-auto">
          {execution_events.length === 0 ? (
            <div className="p-8 text-center text-muted text-sm italic">Sin eventos de ejecución.</div>
          ) : (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-white/5 text-muted">
                  {['ID', 'Acción', 'Estado', 'Timestamp'].map(h => (
                    <th key={h} className="text-left p-3 text-[9px] uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {execution_events.map(e => (
                  <tr key={e.execution_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                    <td className="p-3 text-muted">{e.execution_id.slice(0, 8)}</td>
                    <td className="p-3 text-white">{e.action_type}</td>
                    <td className="p-3 text-[#00aaff]">{e.status}</td>
                    <td className="p-3 text-muted">{e.timestamp ? new Date(e.timestamp).toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── HUMAN ACTIONS TAB ────────────────────────────────────── */}
      {activeTab === 'human' && (
        <div className="card-dash overflow-x-auto">
          {human_events.length === 0 ? (
            <div className="p-8 text-center text-muted text-sm italic">Sin acciones humanas.</div>
          ) : (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-white/5 text-muted">
                  {['ID', 'Tipo', 'Actor', 'Razón', 'Timestamp'].map(h => (
                    <th key={h} className="text-left p-3 text-[9px] uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {human_events.map(e => (
                  <tr key={e.action_event_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                    <td className="p-3 text-muted">{e.action_event_id.slice(0, 8)}</td>
                    <td className="p-3 text-white">{e.action_type}</td>
                    <td className="p-3 text-[#ffaa00]">{e.actor}</td>
                    <td className="p-3 text-muted">{e.reason || '—'}</td>
                    <td className="p-3 text-muted">{e.timestamp ? new Date(e.timestamp).toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
