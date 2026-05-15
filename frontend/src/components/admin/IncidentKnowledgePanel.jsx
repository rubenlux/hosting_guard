import React, { useState, useEffect } from 'react';
import {
  Book, Search, Shield, ShieldAlert, ShieldCheck,
  CheckCircle2, XCircle, ChevronDown, ChevronRight,
  Loader2, AlertTriangle, FileText,
} from 'lucide-react';
import {
  listKnowledgeRunbooks,
  getKnowledgeRunbook,
  matchKnowledgeIncident,
  validateKnowledgeSafeAction,
  listKnowledgeSafeActions,
} from '../../services/api';

// ── Severity badge ─────────────────────────────────────────────────────────────

const SEVERITY_STYLE = {
  critical: 'bg-red-500/15 text-red-400 border border-red-500/30',
  high:     'bg-orange-500/15 text-orange-400 border border-orange-500/30',
  medium:   'bg-amber-500/15 text-amber-400 border border-amber-500/30',
  low:      'bg-blue-500/15 text-blue-400 border border-blue-500/30',
};

function SeverityBadge({ severity }) {
  const cls = SEVERITY_STYLE[severity] || 'bg-white/8 text-gray-400 border border-white/10';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${cls}`}>
      {severity || 'unknown'}
    </span>
  );
}

// ── Error display ──────────────────────────────────────────────────────────────

function parseError(err) {
  if (!err) return 'Error desconocido';
  if (err?.response?.status === 401) return 'No autenticado';
  if (err?.response?.status === 403) return 'Sin permisos';
  if (err?.response?.data?.detail) return err.response.data.detail;
  return err.message || 'Error desconocido';
}

// ── Section A: Buscar diagnóstico ─────────────────────────────────────────────

const INCIDENT_TYPES = [
  '', 'WELCOME_TO_NGINX_EMPTY_SITE', 'CONTAINER_WITH_EMPTY_MOUNTS',
  'WORDPRESS_CONFIG_MISSING', 'DB_CONNECTION_ERROR', 'SSL_CERT_EXPIRED',
  'TRAEFIK_ROUTER_MISSING', 'STATIC_NGINX_MISCONFIGURED',
];

function SearchSection() {
  const [text, setText] = useState('');
  const [incidentType, setIncidentType] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [fullRunbook, setFullRunbook] = useState(null);
  const [loadingRunbook, setLoadingRunbook] = useState(false);
  const [runbookError, setRunbookError] = useState(null);
  const [showBody, setShowBody] = useState(false);

  const handleSearch = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setFullRunbook(null);
    setShowBody(false);
    try {
      const data = await matchKnowledgeIncident(text.trim(), incidentType || null);
      setResult(data);
    } catch (err) {
      setError(parseError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleLoadFullRunbook = async () => {
    const id = result?.matched_runbook?.incident_id;
    if (!id) return;
    setLoadingRunbook(true);
    setRunbookError(null);
    try {
      const data = await getKnowledgeRunbook(id);
      setFullRunbook(data);
      setShowBody(true);
    } catch (err) {
      setRunbookError(parseError(err));
    } finally {
      setLoadingRunbook(false);
    }
  };

  const rb = result?.matched_runbook;

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2">
        <Search className="w-4 h-4 text-blue-400" />
        Buscar diagnóstico
      </h2>

      <textarea
        data-testid="knowledge-search-textarea"
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder="Pegar log, error o salida de herramienta…"
        className="w-full h-28 rounded-lg bg-white/5 border border-white/8 px-3 py-2 text-xs text-gray-200 placeholder-gray-600 resize-none focus:outline-none focus:border-blue-500/40"
      />

      <div className="flex items-center gap-3">
        <select
          value={incidentType}
          onChange={e => setIncidentType(e.target.value)}
          className="text-xs bg-white/5 border border-white/8 rounded-lg px-2 py-1.5 text-gray-300 focus:outline-none focus:border-blue-500/40"
        >
          <option value="">Tipo de incidente (opcional)</option>
          {INCIDENT_TYPES.filter(Boolean).map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>

        <button
          data-testid="knowledge-search-btn"
          onClick={handleSearch}
          disabled={loading || !text.trim()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium transition-colors"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
          Buscar runbook
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/25 bg-red-500/8 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}

      {result && (
        <div
          data-testid="knowledge-match-result"
          className="rounded-lg border border-white/8 bg-white/3 px-4 py-3 flex flex-col gap-3"
        >
          {rb ? (
            <>
              <div className="flex items-center gap-2 flex-wrap">
                <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="font-mono text-sm text-white font-semibold">{rb.incident_id}</span>
                <SeverityBadge severity={rb.severity} />
                {result.confidence != null && (
                  <span className="text-[10px] text-gray-500 ml-1">
                    {Math.round(result.confidence * 100)}% confianza
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-gray-400">
                {result.match_method && (
                  <span>Método: <span className="text-gray-300 font-mono">{result.match_method}</span></span>
                )}
                {rb.signature_matched && (
                  <span>Firma: <span className="text-gray-300 font-mono text-[10px]">{rb.signature_matched}</span></span>
                )}
                <span>Auto-repair:
                  <span className={rb.auto_repair_allowed ? ' text-emerald-400' : ' text-gray-400'}>
                    {' '}{rb.auto_repair_allowed ? 'Permitido' : 'Requiere aprobación'}
                  </span>
                </span>
              </div>

              {rb.safe_actions?.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] text-gray-500">Acciones seguras:</span>
                  {rb.safe_actions.map(a => (
                    <span key={a} className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/12 border border-emerald-500/25 text-emerald-400 font-mono">
                      {a}
                    </span>
                  ))}
                </div>
              )}

              {rb.forbidden_actions?.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] text-gray-500">Prohibidas:</span>
                  {rb.forbidden_actions.map(a => (
                    <span key={a} className="text-[10px] px-2 py-0.5 rounded-full bg-red-500/12 border border-red-500/25 text-red-400 font-mono">
                      {a}
                    </span>
                  ))}
                </div>
              )}

              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={handleLoadFullRunbook}
                  disabled={loadingRunbook}
                  className="flex items-center gap-1.5 px-3 py-1 rounded-lg border border-white/10 bg-white/5 hover:bg-white/8 text-xs text-gray-300 transition-colors disabled:opacity-50"
                >
                  {loadingRunbook
                    ? <Loader2 className="w-3 h-3 animate-spin" />
                    : <Book className="w-3 h-3" />}
                  Ver runbook completo
                </button>

                {fullRunbook && (
                  <button
                    onClick={() => setShowBody(v => !v)}
                    className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                  >
                    {showBody ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                    {showBody ? 'Ocultar' : 'Mostrar'}
                  </button>
                )}
              </div>

              {runbookError && (
                <p className="text-xs text-red-400">{runbookError}</p>
              )}

              {fullRunbook && showBody && (
                <pre className="text-[11px] text-gray-300 whitespace-pre-wrap bg-white/3 rounded-lg border border-white/8 p-3 overflow-auto max-h-64 leading-relaxed">
                  {fullRunbook.body}
                </pre>
              )}
            </>
          ) : (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
              Sin runbook coincidente
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Section B: Runbooks ────────────────────────────────────────────────────────

function RunbooksSection() {
  const [runbooks, setRunbooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterText, setFilterText] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('all');
  const [filterAutoRepair, setFilterAutoRepair] = useState('all');
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState(null);

  useEffect(() => {
    listKnowledgeRunbooks()
      .then(data => setRunbooks(data.runbooks || []))
      .catch(err => setError(parseError(err)))
      .finally(() => setLoading(false));
  }, []);

  const filtered = runbooks.filter(r => {
    if (filterText && !r.incident_id.toLowerCase().includes(filterText.toLowerCase())) return false;
    if (filterSeverity !== 'all' && r.severity !== filterSeverity) return false;
    if (filterAutoRepair === 'sí' && !r.auto_repair_allowed) return false;
    if (filterAutoRepair === 'no' && r.auto_repair_allowed) return false;
    return true;
  });

  const handleRowClick = async (rb) => {
    if (selected === rb.incident_id) {
      setSelected(null);
      setDetail(null);
      return;
    }
    setSelected(rb.incident_id);
    setDetail(null);
    setDetailError(null);
    setLoadingDetail(true);
    try {
      const data = await getKnowledgeRunbook(rb.incident_id);
      setDetail(data);
    } catch (err) {
      setDetailError(parseError(err));
    } finally {
      setLoadingDetail(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2">
        <Book className="w-4 h-4 text-purple-400" />
        Runbooks
      </h2>

      <div className="flex items-center gap-3 flex-wrap">
        <input
          type="text"
          value={filterText}
          onChange={e => setFilterText(e.target.value)}
          placeholder="Filtrar por nombre…"
          className="flex-1 min-w-[160px] text-xs bg-white/5 border border-white/8 rounded-lg px-3 py-1.5 text-gray-300 placeholder-gray-600 focus:outline-none focus:border-blue-500/40"
        />
        <select
          value={filterSeverity}
          onChange={e => setFilterSeverity(e.target.value)}
          className="text-xs bg-white/5 border border-white/8 rounded-lg px-2 py-1.5 text-gray-300 focus:outline-none focus:border-blue-500/40"
        >
          <option value="all">Severidad: Todas</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select
          value={filterAutoRepair}
          onChange={e => setFilterAutoRepair(e.target.value)}
          className="text-xs bg-white/5 border border-white/8 rounded-lg px-2 py-1.5 text-gray-300 focus:outline-none focus:border-blue-500/40"
        >
          <option value="all">Auto-repair: Todos</option>
          <option value="sí">Sí</option>
          <option value="no">No</option>
        </select>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-xs text-gray-500 py-4">
          <Loader2 className="w-4 h-4 animate-spin" />
          Cargando runbooks…
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/25 bg-red-500/8 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}

      {!loading && !error && (
        <div data-testid="knowledge-runbooks-list" className="flex flex-col gap-1">
          {filtered.length === 0 && (
            <p className="text-xs text-gray-500 py-3 text-center">Sin resultados</p>
          )}
          {filtered.map(rb => (
            <div key={rb.incident_id} className="flex flex-col">
              <button
                data-testid="knowledge-runbook-row"
                onClick={() => handleRowClick(rb)}
                className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/3 hover:bg-white/6 border border-white/6 text-left transition-colors"
              >
                <FileText className="w-3.5 h-3.5 text-gray-500 shrink-0" />
                <span className="font-mono text-xs text-white flex-1 truncate">{rb.incident_id}</span>
                <SeverityBadge severity={rb.severity} />
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${rb.auto_repair_allowed ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/8' : 'text-gray-400 border-white/10 bg-white/3'}`}>
                  {rb.auto_repair_allowed ? 'Auto-repair' : 'Manual'}
                </span>
                <span className="text-[10px] text-gray-600">
                  {(rb.safe_actions?.length || 0)}s / {(rb.forbidden_actions?.length || 0)}f
                </span>
                {selected === rb.incident_id
                  ? <ChevronDown className="w-3.5 h-3.5 text-gray-500 shrink-0" />
                  : <ChevronRight className="w-3.5 h-3.5 text-gray-500 shrink-0" />}
              </button>

              {selected === rb.incident_id && (
                <div
                  data-testid="knowledge-runbook-detail"
                  className="border border-white/6 border-t-0 rounded-b-lg bg-[#0d0d0f] px-4 py-3 flex flex-col gap-3"
                >
                  {loadingDetail && (
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Cargando detalle…
                    </div>
                  )}
                  {detailError && (
                    <p className="text-xs text-red-400">{detailError}</p>
                  )}
                  {detail && (
                    <>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-sm text-white font-semibold">{detail.incident_id}</span>
                        <SeverityBadge severity={detail.severity} />
                      </div>
                      {detail.safe_actions?.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-[10px] text-gray-500">Seguras:</span>
                          {detail.safe_actions.map(a => (
                            <span key={a} className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/12 border border-emerald-500/25 text-emerald-400 font-mono">{a}</span>
                          ))}
                        </div>
                      )}
                      {detail.forbidden_actions?.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-[10px] text-gray-500">Prohibidas:</span>
                          {detail.forbidden_actions.map(a => (
                            <span key={a} className="text-[10px] px-2 py-0.5 rounded-full bg-red-500/12 border border-red-500/25 text-red-400 font-mono">{a}</span>
                          ))}
                        </div>
                      )}
                      {detail.body && (
                        <pre className="text-[11px] text-gray-300 whitespace-pre-wrap bg-white/3 rounded-lg border border-white/8 p-3 overflow-auto max-h-64 leading-relaxed">
                          {detail.body}
                        </pre>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Section C: Safe Action Validator ──────────────────────────────────────────

function SafeActionValidatorSection() {
  const [safeActions, setSafeActions] = useState([]);
  const [loadingActions, setLoadingActions] = useState(true);
  const [actionsError, setActionsError] = useState(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [actionId, setActionId] = useState('');
  const [contextText, setContextText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    setLoadingActions(true);
    listKnowledgeSafeActions()
      .then(data => {
        setSafeActions(data.safe_actions || []);
        setActionsError(null);
      })
      .catch(err => setActionsError(parseError(err)))
      .finally(() => setLoadingActions(false));
  }, []);

  const handleValidate = async () => {
    if (!actionId.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    let parsedContext = null;
    if (contextText.trim()) {
      try {
        parsedContext = JSON.parse(contextText.trim());
      } catch {
        setError('El contexto JSON no es válido');
        setLoading(false);
        return;
      }
    }
    try {
      const data = await validateKnowledgeSafeAction(actionId.trim(), parsedContext);
      setResult(data);
    } catch (err) {
      setError(parseError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2">
        <Shield className="w-4 h-4 text-amber-400" />
        Validador de acción segura
      </h2>

      {actionsError && (
        <div className="rounded-lg border border-red-500/25 bg-red-500/8 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          Error cargando acciones: {actionsError}
        </div>
      )}

      <div className="flex items-center gap-3 flex-wrap">
        {loadingActions ? (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Cargando acciones…
          </div>
        ) : safeActions.length > 0 ? (
          <div className="relative flex-1 min-w-[200px]">
            <button
              data-testid="knowledge-safe-action-select"
              type="button"
              onClick={() => setDropdownOpen(v => !v)}
              className="w-full text-left text-xs bg-[#111] border border-white/10 rounded-lg px-3 py-1.5 text-gray-200 flex items-center justify-between gap-2 hover:border-white/20 focus:outline-none focus:border-blue-500/40 transition-colors"
            >
              <span className={actionId ? 'text-gray-100 font-mono' : 'text-gray-500'}>
                {actionId || 'Seleccionar acción…'}
              </span>
              <ChevronDown className="w-3.5 h-3.5 text-gray-500 shrink-0" />
            </button>
            {dropdownOpen && (
              <div className="absolute top-full left-0 right-0 mt-1 z-50 rounded-lg border border-white/10 bg-[#111] shadow-xl overflow-auto max-h-56">
                <button
                  type="button"
                  onClick={() => { setActionId(''); setDropdownOpen(false); }}
                  className="w-full text-left px-3 py-2 text-xs text-gray-500 hover:bg-white/5 border-b border-white/5"
                >
                  Seleccionar acción…
                </button>
                {safeActions.map(a => (
                  <button
                    key={a.action_id}
                    data-testid={`knowledge-safe-action-option-${a.action_id}`}
                    type="button"
                    onClick={() => { setActionId(a.action_id); setDropdownOpen(false); }}
                    className={`w-full text-left px-3 py-2 text-xs font-mono hover:bg-white/8 transition-colors ${actionId === a.action_id ? 'text-blue-400 bg-blue-500/8' : 'text-gray-200'}`}
                  >
                    {a.action_id}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <input
            data-testid="knowledge-safe-action-select"
            type="text"
            value={actionId}
            onChange={e => setActionId(e.target.value)}
            placeholder="ID de acción…"
            className="flex-1 min-w-[200px] text-xs bg-white/5 border border-white/8 rounded-lg px-3 py-1.5 text-gray-300 placeholder-gray-600 focus:outline-none focus:border-blue-500/40"
          />
        )}
      </div>

      <textarea
        value={contextText}
        onChange={e => setContextText(e.target.value)}
        placeholder='Contexto JSON opcional, ej: {"hosting_id": 42}'
        className="w-full h-20 rounded-lg bg-white/5 border border-white/8 px-3 py-2 text-xs text-gray-200 placeholder-gray-600 resize-none font-mono focus:outline-none focus:border-blue-500/40"
      />

      <button
        data-testid="knowledge-safe-action-btn"
        onClick={handleValidate}
        disabled={loading || !actionId.trim()}
        className="self-start flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium transition-colors"
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
        Validar acción
      </button>

      {error && (
        <div className="rounded-lg border border-red-500/25 bg-red-500/8 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}

      {result && (
        <div
          data-testid="knowledge-safe-action-result"
          className="rounded-lg border border-white/8 bg-white/3 px-4 py-3 flex flex-col gap-2"
        >
          <div className="flex items-center gap-2">
            {result.allowed
              ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              : <XCircle className="w-4 h-4 text-red-400" />}
            <span className={`text-sm font-semibold ${result.allowed ? 'text-emerald-400' : 'text-red-400'}`}>
              {result.allowed ? 'Permitida' : 'Denegada'}
            </span>
          </div>
          {result.reason && (
            <p className="text-xs text-gray-300">{result.reason}</p>
          )}
          <div className="flex flex-wrap gap-3 text-[10px] text-gray-500">
            {result.requires_dry_run_first !== undefined && (
              <span>Dry-run primero: <span className={result.requires_dry_run_first ? 'text-amber-400' : 'text-gray-400'}>{result.requires_dry_run_first ? 'Sí' : 'No'}</span></span>
            )}
            {result.requires_human_approval !== undefined && (
              <span>Aprobación humana: <span className={result.requires_human_approval ? 'text-amber-400' : 'text-gray-400'}>{result.requires_human_approval ? 'Sí' : 'No'}</span></span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Section D: Postmortems ────────────────────────────────────────────────────

const POSTMORTEMS = [
  {
    date: '2026-05-14',
    title: 'Traefik routing & static container incident',
    related_incident_id: 'WELCOME_TO_NGINX_EMPTY_SITE',
    file: 'postmortem_2026-05-14_traefik_static.md',
  },
];

function PostmortemsSection({ onSearchIncident }) {
  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2">
        <FileText className="w-4 h-4 text-gray-400" />
        Postmortems
      </h2>

      <p className="text-[11px] text-gray-500">
        Los postmortems están en <span className="font-mono text-gray-400">docs/incidents/postmortems/</span>
      </p>

      <div className="flex flex-col gap-2">
        {POSTMORTEMS.map(pm => (
          <div
            key={pm.file}
            className="flex items-start justify-between gap-3 rounded-lg border border-white/6 bg-white/3 px-4 py-3"
          >
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] text-gray-500 font-mono">{pm.date}</span>
              <span className="text-xs text-gray-200 font-medium">{pm.title}</span>
              <span className="text-[10px] text-gray-600 font-mono">{pm.file}</span>
            </div>
            <button
              onClick={() => onSearchIncident && onSearchIncident(pm.related_incident_id)}
              className="shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-blue-500/25 bg-blue-500/8 hover:bg-blue-500/15 text-[11px] text-blue-400 transition-colors"
            >
              <Book className="w-3 h-3" />
              Ver runbook relacionado
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'search',    label: 'Buscar diagnóstico', icon: Search },
  { id: 'runbooks',  label: 'Runbooks',           icon: Book },
  { id: 'validator', label: 'Validar acción',      icon: Shield },
  { id: 'postmortems', label: 'Postmortems',       icon: FileText },
];

// ── Main panel ────────────────────────────────────────────────────────────────

export default function IncidentKnowledgePanel() {
  const [tab, setTab] = useState('search');
  const [jumpToSearch, setJumpToSearch] = useState(null);

  // Used from postmortems: switch to runbooks tab and highlight incident
  const handleSearchIncident = (incident_id) => {
    setTab('runbooks');
    setJumpToSearch(incident_id);
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/20">
          <Book className="w-5 h-5 text-blue-400" />
        </div>
        <div>
          <h1 className="text-base font-semibold text-white">Base de Incidentes</h1>
          <p className="text-[11px] text-gray-500">Runbooks, diagnósticos y validación de acciones seguras</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 p-1 rounded-lg bg-white/4 border border-white/6 w-fit">
        {TABS.map(t => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                tab === t.id
                  ? 'bg-white/10 text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="rounded-xl border border-white/8 bg-[#111] px-6 py-5">
        {tab === 'search'    && <SearchSection />}
        {tab === 'runbooks'  && <RunbooksSection jumpToId={jumpToSearch} />}
        {tab === 'validator' && <SafeActionValidatorSection />}
        {tab === 'postmortems' && <PostmortemsSection onSearchIncident={handleSearchIncident} />}
      </div>
    </div>
  );
}
