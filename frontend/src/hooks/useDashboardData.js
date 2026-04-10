import { useState, useEffect, useRef } from 'react';
import api from '../services/api';

// ── Utilities ─────────────────────────────────────────────────────────────────

function timeAgo(iso) {
  if (!iso) return '';
  const s = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

function normalizeRealtime(data) {
  const last     = data?.recent_pages?.[0];
  const lastPath = last?.url?.replace(/^https?:\/\/[^/]+/, '') || null;
  return {
    active:   data?.active_users ?? 0,
    lastPath,
    lastTime: last ? timeAgo(last.created_at) : null,
    isLive:   (data?.active_users ?? 0) > 0,
  };
}

// ── Simple in-process cache ───────────────────────────────────────────────────
// Prevents redundant requests when the component re-mounts within staleTime.
// Key: site_id. Value: { data, fetchedAt }.

const _cache = new Map();
const STALE_MS = 30_000; // 30 seconds

function getCached(siteId) {
  const entry = _cache.get(siteId);
  if (!entry) return null;
  if (Date.now() - entry.fetchedAt > STALE_MS) { _cache.delete(siteId); return null; }
  return entry.data;
}

function setCache(siteId, data) {
  // LRU eviction: remove oldest entry instead of nuking the whole cache
  if (_cache.size >= 50) {
    const oldest = _cache.keys().next().value;
    _cache.delete(oldest);
  }
  _cache.set(siteId, { data, fetchedAt: Date.now() });
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Fetches and transforms all data needed by the Dashboard analytics overview.
 *
 * Architecture: 3 independent effects with clear responsibilities:
 *   Effect 1 — fetch site list once; auto-select first site
 *   Effect 2 — fetch dashboard-summary when site or retryCount changes
 *   Effect 3 — realtime polling when site changes
 *
 * Optimisations applied:
 *   [F1] 5 requests → 1 aggregated endpoint (dashboard-summary)
 *   [F2] mounted flag prevents setState after unmount
 *   [F3] computeChips moved to backend — frontend only renders
 *   [F4] Realtime polling pauses when tab is hidden with no active users
 *   [F5] In-process LRU cache with 30s staleTime
 *   [F6] Errors logged and exposed; never swallowed
 *   [F7] sparkline is already normalized to number[] by the backend
 *
 * Returns:
 *   sites       — all registered pixel sites for the user
 *   site        — currently selected site { site_id, name }
 *   selectSite  — (siteId: string) => void — switch the active site
 *   retry       — () => void — invalidate cache + re-fetch current site
 *   kpis        — { visits, sessions, bounceRate, active }
 *   sparkline   — number[] (page_views per day, 7 days)
 *   topPages    — { path, views, url }[] (max 3)
 *   chips       — string[] (max 4, computed on server)
 *   realtime    — { active, lastPath, lastTime, isLive }
 *   loading     — boolean
 *   error       — Error | null
 */
export function useDashboardData() {
  const [sites,     setSites]     = useState([]);
  const [site,      setSite]      = useState(null);
  const [kpis,      setKpis]      = useState(null);
  const [sparkline, setSparkline] = useState([]);
  const [topPages,  setTopPages]  = useState([]);
  const [chips,     setChips]     = useState([]);
  const [realtime,  setRealtime]  = useState({ active: 0, lastPath: null, lastTime: null, isLive: false });
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);
  // retryCount bumped by retry() to re-trigger Effect 2 without changing site
  const [retryCount, setRetryCount] = useState(0);
  // Ref used in polling closure to read latest active count without stale capture [F4]
  const activeRef = useRef(0);

  // ── Effect 1: fetch site list once, auto-select first ─────────────────────
  useEffect(() => {
    let mounted = true;

    api.get('/pixel/sites')
      .then(r => {
        if (!mounted) return;
        const list = r.data || [];
        setSites(list);
        if (list.length > 0) setSite(list[0]); // auto-select; user can change via selectSite
        else setLoading(false);                 // no sites — stop loading, show EmptyState
      })
      .catch(err => {
        if (!mounted) return;
        console.error('[useDashboardData] /pixel/sites failed', err); // [F6]
        setError(err);
        setLoading(false);
      });

    return () => { mounted = false; };
  }, []);

  // ── Effect 2: fetch dashboard-summary when site or retryCount changes ──────
  useEffect(() => {
    if (!site) return;
    let mounted = true;

    const id = site.site_id;
    setLoading(true);
    setError(null);

    // [F5] Serve from cache if fresh (skip on explicit retry — cache already cleared)
    const cached = getCached(id);
    if (cached) {
      applyPayload(cached);
      setLoading(false);
      return;
    }

    // [F1] Single aggregated request instead of 5 parallel ones
    api.get(`/pixel/sites/${id}/dashboard-summary?days=7`)
      .then(res => {
        if (!mounted) return; // [F2]
        setCache(id, res.data); // [F5]
        applyPayload(res.data);
      })
      .catch(err => {
        if (!mounted) return;
        console.error('[useDashboardData] dashboard-summary failed', err); // [F6]
        setError(err);
      })
      .finally(() => { if (mounted) setLoading(false); }); // single source of truth

    return () => { mounted = false; }; // [F2]
  }, [site, retryCount]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Effect 3: realtime polling ────────────────────────────────────────────
  useEffect(() => {
    if (!site) return;
    let mounted = true;

    const poll = () => {
      // [F4] Skip when hidden with no active users — saves ~600 req/min at 100 users
      if (document.hidden && activeRef.current === 0) return;

      api.get(`/pixel/sites/${site.site_id}/realtime`)
        .then(r => {
          if (!mounted) return; // [F2]
          const rt = normalizeRealtime(r.data);
          activeRef.current = rt.active; // keep ref in sync for next poll decision
          setRealtime(rt);
          // [M3] Skip re-render if active count hasn't changed
          setKpis(prev => {
            if (!prev || prev.active === rt.active) return prev;
            return { ...prev, active: rt.active };
          });
        })
        .catch(err => {
          if (!mounted) return;
          console.error('[useDashboardData] realtime poll failed', err); // [F6]
        });
    };

    poll();
    const iv = setInterval(poll, 10_000);
    return () => { mounted = false; clearInterval(iv); }; // [F2]
  }, [site]);

  // ── Helpers exposed to consumers ───────────────────────────────────────────

  function selectSite(siteId) {
    const target = sites.find(s => s.site_id === siteId);
    if (target && target.site_id !== site?.site_id) {
      setSite(target);
    }
  }

  function retry() {
    if (site) _cache.delete(site.site_id); // invalidate so Effect 2 re-fetches
    setRetryCount(c => c + 1);
  }

  // ── [F1-loading] setLoading is NOT called here — .finally() owns it ────────
  function applyPayload(data) {
    const stats = data.stats || {};
    setKpis({
      visits:     stats.today_events      ?? 0,
      sessions:   stats.unique_sessions   ?? 0,
      bounceRate: stats.bounce_rate       ?? 0,
      active:     stats.active_users_5min ?? 0,
    });
    setSparkline(data.sparkline || []); // [F7] already number[]
    setTopPages(data.top_pages  || []); // [F3] already normalized
    setChips(data.chips         || []); // [F3] computed on server
  }

  return {
    sites, site, selectSite, retry,
    kpis, sparkline, topPages, chips, realtime,
    loading, error,
  };
}
