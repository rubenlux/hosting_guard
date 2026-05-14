import React, { useEffect, useState, useCallback } from 'react';
import {
  ShieldCheck, ShieldAlert, AlertTriangle, RefreshCw, Wrench,
  Globe, Server, FileText, Loader2, Clock, WifiOff, Lock,
  ChevronDown, ChevronRight, CircleDot,
} from 'lucide-react';
import {
  getRouterHealthPlatform, checkRouterHealthPlatform, repairRouterHealthPlatform,
  getRouterHealthTenants, repairRouterHealthTenant,
} from '../../services/api';

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmtDate(str) {
  if (!str) return '—';
  return new Date(str).toLocaleString('es-AR', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

const INCIDENT_LABEL = {
  traefik_router_missing_or_unmatched: 'Router faltante',
  traefik_backend_unreachable:         'Backend inaccesible',
  public_route_timeout:                'Timeout',
  tls_or_certificate_issue:            'Error SSL/TLS',
  container_not_running:               'Container caído',
  platform_route_unhealthy:            'Ruta de plataforma caída',
};

const INCIDENT_STYLE = {
  traefik_router_missing_or_unmatched: 'text-red-400 bg-red-500/10 border-red-500/25',
  traefik_backend_unreachable:         'text-orange-400 bg-orange-500/10 border-orange-500/25',
  public_route_timeout:                'text-amber-400 bg-amber-500/10 border-amber-500/25',
  tls_or_certificate_issue:            'text-purple-400 bg-purple-500/10 border-purple-500/25',
  container_not_running:               'text-red-400 bg-red-500/10 border-red-500/25',
  platform_route_unhealthy:            'text-red-400 bg-red-500/10 border-red-500/25',
};

const ROUTER_SOURCE_STYLE = {
  dynamic_file:  'text-emerald-400',
  docker_labels: 'text-blue-400',
  missing:       'text-red-400',
  unknown:       'text-gray-500',
};

function HealthBadge({ healthy, incident_type }) {
  if (healthy === undefined || healthy === null) {
    return <span className="text-xs text-gray-500 font-medium">No verificado</span>;
  }
  if (healthy) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
        <ShieldCheck className="w-3.5 h-3.5" />
        Healthy
      </span>
    );
  }
  const label = INCIDENT_LABEL[incident_type] || incident_type || 'Unhealthy';
  const style = INCIDENT_STYLE[incident_type] || 'text-red-400 bg-red-500/10 border-red-500/25';
  return (
    <span className={`flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full border ${style}`}>
      <ShieldAlert className="w-3 h-3" />
      {label}
    </span>
  );
}

function DynamicFileTag({ visibility, routerSource }) {
  if (visibility === 'visible') {
    return <span className="ml-1 text-emerald-500">(visible)</span>;
  }
  if (visibility === 'not_mounted_in_app') {
    if (routerSource === 'docker_labels') {
      return <span className="ml-1 text-gray-500">(no montado en container — activo por docker labels)</span>;
    }
    return <span className="ml-1 text-amber-400">(no montado en app container)</span>;
  }
  if (visibility === 'absent') {
    if (routerSource === 'docker_labels') {
      return <span className="ml-1 text-gray-500">(sin archivo — ruta activa por docker labels)</span>;
    }
    return <span className="ml-1 text-red-500">(ausente)</span>;
  }
  return null;
}

function StatusCode({ code }) {
  if (code === null || code === undefined) return <span className="text-gray-600 text-xs">—</span>;
  const color = code >= 200 && code < 300 ? 'text-emerald-400'
    : code >= 300 && code < 400 ? 'text-blue-400'
    : code >= 400 ? 'text-red-400'
    : 'text-gray-400';
  return <span className={`text-xs font-mono font-bold ${color}`}>{code}</span>;
}

// ─── Platform Tab ─────────────────────────────────────────────────────────────

function PlatformTab() {
  const [config, setConfig] = useState(null);
  const [results, setResults] = useState(null);
  const [checking, setChecking] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [repairResult, setRepairResult] = useState(null);
  const [error, setError] = useState(null);

  const loadConfig = useCallback(async () => {
    try {
      const data = await getRouterHealthPlatform();
      setConfig(data.platform_routes);
    } catch (e) {
      setError('No se pudo cargar la configuración de rutas.');
    }
  }, []);

  useEffect(() => { loadConfig(); }, [loadConfig]);

  const handleCheck = async () => {
    setChecking(true);
    setError(null);
    setRepairResult(null);
    try {
      const data = await checkRouterHealthPlatform();
      setResults(data);
    } catch (e) {
      setError('Error al verificar rutas de plataforma.');
    } finally {
      setChecking(false);
    }
  };

  const handleRepair = async (dry_run) => {
    setRepairing(true);
    setError(null);
    setRepairResult(null);
    try {
      const data = await repairRouterHealthPlatform(dry_run);
      setRepairResult({ ...data, dry_run });
    } catch (e) {
      setError('Error al reparar rutas de plataforma.');
    } finally {
      setRepairing(false);
    }
  };

  const display = results ? results.results : config ? config.map(r => ({ ...r, healthy: undefined })) : [];

  return (
    <div className="flex flex-col gap-4">
      {/* Summary row */}
      {results && (
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-sm">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span className="text-emerald-400 font-medium">{results.healthy} OK</span>
          </div>
          {results.unhealthy > 0 && (
            <div className="flex items-center gap-2 text-sm">
              <ShieldAlert className="w-4 h-4 text-red-400" />
              <span className="text-red-400 font-medium">{results.unhealthy} con problemas</span>
            </div>
          )}
        </div>
      )}

      {/* Route cards */}
      <div className="flex flex-col gap-2">
        {display.map((route, i) => (
          <div key={route.host || i} className="bg-[#111] border border-white/8 rounded-xl px-4 py-3 flex flex-col gap-2">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <Globe className="w-3.5 h-3.5 text-gray-500 shrink-0" />
                <span className="text-sm font-mono text-white">{route.host}</span>
              </div>
              <div className="flex items-center gap-3">
                {route.public_status_code !== undefined && (
                  <StatusCode code={route.public_status_code} />
                )}
                <HealthBadge healthy={route.healthy} incident_type={route.incident_type} />
              </div>
            </div>

            <div className="flex items-center gap-4 flex-wrap text-[11px] text-gray-500">
              <span>
                Servicio:{' '}
                <span className="text-gray-300 font-mono">{route.service}</span>
              </span>
              <span>
                Router:{' '}
                <span className={`font-medium ${ROUTER_SOURCE_STYLE[route.router_source] || 'text-gray-400'}`}>
                  {route.router_source || '—'}
                </span>
              </span>
              {route.paths && (
                <span>
                  Paths:{' '}
                  <span className="text-gray-400 font-mono">{route.paths.join(', ')}</span>
                </span>
              )}
            </div>

            {route.dynamic_file && (
              <div className="flex items-center gap-1.5 text-[11px]">
                <FileText className="w-3 h-3 text-gray-600" />
                <span className="font-mono text-gray-600">{route.dynamic_file}</span>
                <DynamicFileTag visibility={route.dynamic_file_visibility} routerSource={route.router_source} />
              </div>
            )}

            {route.summary && !route.healthy && (
              <p className="text-xs text-red-400/80 mt-0.5">{route.summary}</p>
            )}

            {route.checked_at && (
              <div className="flex items-center gap-1 text-[10px] text-gray-600">
                <Clock className="w-3 h-3" />
                {fmtDate(route.checked_at)}
              </div>
            )}
          </div>
        ))}

        {!display.length && (
          <div className="text-sm text-gray-500 text-center py-8">
            Cargando configuración…
          </div>
        )}
      </div>

      {/* Repair result */}
      {repairResult && (
        <div className={`rounded-xl border px-4 py-3 text-xs flex flex-col gap-1 ${repairResult.changed ? 'border-amber-500/30 bg-amber-500/8' : 'border-emerald-500/20 bg-emerald-500/8'}`}>
          <p className={`font-semibold ${repairResult.changed ? 'text-amber-400' : 'text-emerald-400'}`}>
            {repairResult.dry_run ? 'Simulación: ' : ''}{repairResult.changed ? 'Cambios detectados' : 'Archivos ya correctos — sin cambios'}
          </p>
          {repairResult.files && Object.entries(repairResult.files).map(([path, info]) => (
            <p key={path} className="font-mono text-gray-400">
              {info.action} — {path.split('/').pop()}
            </p>
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-red-500/25 bg-red-500/8 px-4 py-3 text-xs text-red-400">
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={handleCheck}
          disabled={checking}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1e1e24] border border-white/10 text-xs text-white hover:bg-[#2a2a32] disabled:opacity-50 transition-colors"
        >
          {checking ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Verificar ahora
        </button>
        <button
          onClick={() => handleRepair(true)}
          disabled={repairing}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1e1e24] border border-white/10 text-xs text-amber-300 hover:bg-[#2a2a32] disabled:opacity-50 transition-colors"
        >
          {repairing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CircleDot className="w-3.5 h-3.5" />}
          Simular reparación
        </button>
        <button
          onClick={() => {
            if (window.confirm('¿Reparar archivos de plataforma Traefik? Esto sobrescribirá los archivos (con backup automático).')) {
              handleRepair(false);
            }
          }}
          disabled={repairing}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1e1e24] border border-emerald-500/30 text-xs text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-50 transition-colors"
        >
          {repairing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wrench className="w-3.5 h-3.5" />}
          Reparar rutas de plataforma
        </button>
      </div>
    </div>
  );
}

// ─── Tenants Tab ──────────────────────────────────────────────────────────────

function _parseRepairError(e) {
  const detail = e.response?.data?.detail;
  if (detail && typeof detail === 'object') return detail;
  if (typeof detail === 'string') return { code: 'repair_error', message: detail };
  return { code: 'repair_error', message: 'Error al reparar router' };
}

function TenantRepairButtons({ r, onRepairDone }) {
  const [repairing, setRepairing] = useState(false);
  const [repairResult, setRepairResult] = useState(null);
  const [repairError, setRepairError] = useState(null); // { code, message, repair_available? }

  const canRepair = r.incident_type === 'traefik_router_missing_or_unmatched';
  const liveDisabled = repairing || repairError?.repair_available === false;

  const handleRepair = async (dry_run) => {
    if (!dry_run && !window.confirm(
      'Esto solo recrea la ruta Traefik del sitio.\n\n' +
      'No modifica archivos, contenedores, DNS ni datos del cliente.\n\n' +
      '¿Confirmar reparación?'
    )) return;

    setRepairing(true);
    setRepairResult(null);
    setRepairError(null);
    try {
      const res = await repairRouterHealthTenant(r.hosting_id, dry_run);
      setRepairResult({ ...res, dry_run });
      if (!dry_run) onRepairDone?.();
    } catch (e) {
      setRepairError(_parseRepairError(e));
    } finally {
      setRepairing(false);
    }
  };

  if (!canRepair) return null;

  return (
    <div className="flex flex-col gap-2 mt-2">
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => handleRepair(true)}
          disabled={repairing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1e1e24] border border-white/10 text-xs text-amber-300 hover:bg-[#2a2a32] disabled:opacity-50 transition-colors"
        >
          {repairing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <AlertTriangle className="w-3.5 h-3.5" />}
          Simular reparación
        </button>
        <button
          onClick={() => handleRepair(false)}
          disabled={liveDisabled}
          title={liveDisabled && !repairing ? 'Reparación desde UI no disponible. Ver mensaje de error.' : undefined}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1e1e24] border text-xs transition-colors
            ${liveDisabled
              ? 'border-white/10 text-gray-600 cursor-not-allowed opacity-50'
              : 'border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10'}`}
        >
          {repairing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Globe className="w-3.5 h-3.5" />}
          Reparar router
        </button>
      </div>

      {repairResult && (
        <div className={`rounded-lg border px-3 py-2 text-xs flex flex-col gap-1 ${repairResult.action === 'unchanged' ? 'border-emerald-500/20 bg-emerald-500/8' : 'border-amber-500/30 bg-amber-500/8'}`}>
          <p className={`font-semibold ${repairResult.action === 'unchanged' ? 'text-emerald-400' : 'text-amber-400'}`}>
            {repairResult.dry_run ? 'Simulación: ' : ''}{repairResult.action === 'unchanged' ? 'Archivo ya correcto' : `Acción: ${repairResult.action}`}
          </p>
          <p className="font-mono text-gray-500">{repairResult.file_path}</p>
          {repairResult.yaml && (
            <details className="mt-1">
              <summary className="cursor-pointer text-gray-500 hover:text-gray-300">Ver YAML generado</summary>
              <pre className="mt-1 text-[10px] text-green-400 bg-black/40 p-2 rounded overflow-x-auto">{repairResult.yaml}</pre>
            </details>
          )}
        </div>
      )}
      {repairError && (
        <div className="rounded-lg border border-red-500/25 bg-red-500/8 px-3 py-2 text-xs flex flex-col gap-1">
          {repairError.code === 'traefik_dynamic_path_not_writable' ? (
            <>
              <p className="text-amber-400 font-semibold">Reparación desde UI no habilitada</p>
              <p className="text-gray-400">
                El contenedor backend no puede escribir rutas Traefik.
                Montá <code className="text-gray-300">/opt/traefik-dynamic</code> como <code className="text-gray-300">:rw</code> en docker-compose,
                o ejecutá el script de reparación a nivel host.
              </p>
              <p className="text-gray-600 mt-0.5">Simular reparación sigue disponible para previsualizar el YAML.</p>
            </>
          ) : (
            <p className="text-red-400">{repairError.message}</p>
          )}
        </div>
      )}
    </div>
  );
}

function TenantsTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [unhealthyOnly, setUnhealthyOnly] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getRouterHealthTenants({ unhealthy_only: unhealthyOnly });
      setData(res);
    } catch (e) {
      setError('Error al verificar rutas de clientes.');
    } finally {
      setLoading(false);
    }
  }, [unhealthyOnly]);

  useEffect(() => { load(); }, [load]);

  const results = data?.results || [];

  return (
    <div className="flex flex-col gap-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          {data && (
            <div className="flex items-center gap-3 text-sm">
              <span className="text-emerald-400">{data.healthy} OK</span>
              {data.unhealthy > 0 && (
                <span className="text-red-400">{data.unhealthy} con problemas</span>
              )}
              <span className="text-gray-600 text-xs">/ {data.total} total</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={unhealthyOnly}
              onChange={e => setUnhealthyOnly(e.target.checked)}
              className="accent-red-400"
            />
            Solo con problemas
          </label>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1e1e24] border border-white/10 text-xs text-white hover:bg-[#2a2a32] disabled:opacity-50 transition-colors"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Verificar
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/25 bg-red-500/8 px-4 py-3 text-xs text-red-400">
          {error}
        </div>
      )}

      {/* Results table */}
      <div className="flex flex-col gap-1.5">
        {results.length === 0 && !loading && (
          <div className="text-sm text-gray-500 text-center py-10">
            {unhealthyOnly ? 'No hay sitios con problemas.' : 'No hay sitios activos para verificar.'}
          </div>
        )}

        {results.map(r => {
          const isOpen = expanded === r.hosting_id;
          return (
            <div key={r.hosting_id} className="bg-[#111] border border-white/8 rounded-xl overflow-hidden">
              <button
                onClick={() => setExpanded(isOpen ? null : r.hosting_id)}
                className="w-full px-4 py-3 flex items-center justify-between gap-3 hover:bg-white/3 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Server className="w-3.5 h-3.5 text-gray-500 shrink-0" />
                  <span className="text-sm font-mono text-white truncate">{r.host}</span>
                  <span className="text-[10px] text-gray-600 shrink-0">#{r.hosting_id}</span>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <StatusCode code={r.public_status_code} />
                  <HealthBadge healthy={r.healthy} incident_type={r.incident_type} />
                  {isOpen ? <ChevronDown className="w-3.5 h-3.5 text-gray-500" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-500" />}
                </div>
              </button>

              {isOpen && (
                <div className="border-t border-white/5 px-4 py-3 flex flex-col gap-2 text-xs">
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-gray-400">
                    <span>Container: <span className="text-gray-300 font-mono">{r.container_name || '—'}</span></span>
                    <span>Router: <span className={`font-medium ${ROUTER_SOURCE_STYLE[r.router_source] || ''}`}>{r.router_source || '—'}</span></span>
                    <span>Container running: <span className={r.container_running === true ? 'text-emerald-400' : 'text-red-400'}>{r.container_running === null ? '?' : r.container_running ? 'Sí' : 'No'}</span></span>
                    <span>Content-type: <span className="text-gray-400 font-mono">{r.content_type || '—'}</span></span>
                  </div>
                  {r.summary && (
                    <p className={`mt-1 leading-relaxed ${r.healthy ? 'text-gray-500' : 'text-red-400/80'}`}>{r.summary}</p>
                  )}
                  {r.checked_at && (
                    <div className="flex items-center gap-1 text-[10px] text-gray-600 mt-1">
                      <Clock className="w-3 h-3" />
                      {fmtDate(r.checked_at)}
                    </div>
                  )}
                  <TenantRepairButtons r={r} onRepairDone={load} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Main panel ───────────────────────────────────────────────────────────────

const TABS = [
  { id: 'platform', label: 'Plataforma' },
  { id: 'tenants',  label: 'Sitios de clientes' },
];

export default function RouterHealthPanel() {
  const [tab, setTab] = useState('platform');

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-white font-semibold text-base flex items-center gap-2">
            <Globe className="w-4 h-4 text-blue-400" />
            Router Health
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Verifica rutas Traefik de plataforma y sitios de clientes.
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-white/8 pb-0">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-xs font-medium border-b-2 transition-colors ${
              tab === t.id
                ? 'border-blue-400 text-blue-400'
                : 'border-transparent text-gray-500 hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'platform' && <PlatformTab />}
      {tab === 'tenants' && <TenantsTab />}
    </div>
  );
}
