import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../services/api';
import { getAdminPixelOverview, getAdminPixelEvents } from '../services/api';

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * All data fetching and state for PixelAnalytics.
 * PixelAnalytics.jsx becomes pure composition — zero fetch logic.
 *
 * Architecture notes:
 *   - Site list + analytics charts are two separate concerns with independent lifecycles
 *   - fetchAllCharts uses mounted flag to prevent setState after unmount/site-switch
 *   - fetchAllCharts polls every 30s but pauses when tab is hidden
 *   - CRUD operations (create, delete) are exposed as callbacks so the component
 *     doesn't need to know the API URLs
 *
 * Returns:
 *   sites, sitesLoading
 *   selectedSite, setSelectedSite
 *   days, setDays
 *   stats, timeseries, devices, countries, pages, chartsLoading
 *   adminStats, adminOverview, adminEvents
 *   createSite(name, domain) → Promise
 *   deleteSite(siteId)       → Promise
 *   copySnippet(siteId)      — writes to clipboard; returns void
 *   copiedSiteId             — siteId currently showing "copied" state (or null)
 */
export function usePixelAnalyticsData(userRole) {
  // ── Site management ────────────────────────────────────────────────────────
  const [sites,       setSites]       = useState([]);
  const [sitesLoading,setSitesLoading]= useState(true);
  const [selectedSite,setSelectedSite]= useState(null);
  const selectedSiteRef = useRef(null); // sync ref so effects can read latest without deps

  useEffect(() => { selectedSiteRef.current = selectedSite; }, [selectedSite]);

  // ── Chart data ─────────────────────────────────────────────────────────────
  const [days,         setDays]         = useState(30);
  const [stats,        setStats]        = useState(null);
  const [timeseries,   setTimeseries]   = useState(null);
  const [devices,      setDevices]      = useState(null);
  const [countries,    setCountries]    = useState(null);
  const [pages,        setPages]        = useState(null);
  const [chartsLoading,setChartsLoading]= useState(false);

  // ── Admin ──────────────────────────────────────────────────────────────────
  const [adminStats,   setAdminStats]   = useState(null);
  const [adminOverview,setAdminOverview]= useState(null);
  const [adminEvents,  setAdminEvents]  = useState([]);

  // ── Clipboard ──────────────────────────────────────────────────────────────
  const [copiedSiteId, setCopiedSiteId] = useState(null);

  // ── Fetch: site list ───────────────────────────────────────────────────────
  const fetchSites = useCallback(async () => {
    setSitesLoading(true);
    try {
      const { data } = await api.get('/pixel/sites');
      setSites(data);
      // Auto-select first site only on initial load (when nothing is selected yet)
      if (data.length > 0 && !selectedSiteRef.current) {
        setSelectedSite(data[0]);
      }
    } catch (err) {
      console.error('[usePixelAnalyticsData] fetchSites failed', err);
    } finally {
      setSitesLoading(false);
    }
  }, []);

  // ── Fetch: admin stats ─────────────────────────────────────────────────────
  const fetchAdminStats = useCallback(async () => {
    if (userRole !== 'admin') return;
    try {
      const { data } = await api.get('/pixel/admin/stats');
      setAdminStats(data);
      const [overview, events] = await Promise.all([
        getAdminPixelOverview(),
        getAdminPixelEvents(50, 0),
      ]);
      setAdminOverview(overview);
      setAdminEvents(events);
    } catch (err) {
      console.error('[usePixelAnalyticsData] fetchAdminStats failed', err);
    }
  }, [userRole]);

  // ── Fetch: chart data for selected site + period ───────────────────────────
  const fetchAllCharts = useCallback(async (siteId, d) => {
    setChartsLoading(true);
    try {
      const [statsRes, tsRes, devRes, cntRes, pgRes] = await Promise.all([
        api.get(`/pixel/sites/${siteId}/stats?days=${d}`),
        api.get(`/pixel/sites/${siteId}/timeseries?days=${d}`),
        api.get(`/pixel/sites/${siteId}/devices?days=${d}`),
        api.get(`/pixel/sites/${siteId}/countries?days=${d}`),
        api.get(`/pixel/sites/${siteId}/pages?days=${d}`),
      ]);
      setStats(statsRes.data);
      setTimeseries(tsRes.data);
      setDevices(devRes.data);
      setCountries(cntRes.data);
      setPages(pgRes.data);
    } catch (err) {
      console.error('[usePixelAnalyticsData] fetchAllCharts failed', err);
    } finally {
      setChartsLoading(false);
    }
  }, []);

  // ── Effects ────────────────────────────────────────────────────────────────

  // Initial load
  useEffect(() => {
    fetchSites();
    fetchAdminStats();
  }, [fetchSites, fetchAdminStats]);

  // Reload charts when site or period changes; poll every 30s, pause when hidden
  useEffect(() => {
    if (!selectedSite) return;
    let mounted = true;

    const id = selectedSite.site_id;
    // Clear stale data immediately so charts show loading state
    setStats(null); setTimeseries(null); setDevices(null);
    setCountries(null); setPages(null);

    const poll = () => {
      if (!mounted) return;
      if (document.hidden) return; // skip when tab is inactive
      fetchAllCharts(id, days);
    };

    poll();
    const iv = setInterval(poll, 30_000);
    return () => { mounted = false; clearInterval(iv); };
  }, [selectedSite, days, fetchAllCharts]);

  // ── CRUD operations ────────────────────────────────────────────────────────

  const createSite = useCallback(async (name, domain) => {
    await api.post('/pixel/sites', { name, domain });
    await fetchSites();
  }, [fetchSites]);

  const deleteSite = useCallback(async (siteId) => {
    await api.delete(`/pixel/sites/${siteId}`);
    if (selectedSiteRef.current?.site_id === siteId) {
      setSelectedSite(null);
      setStats(null);
    }
    await fetchSites();
  }, [fetchSites]);

  const copySnippet = useCallback((siteId) => {
    navigator.clipboard.writeText(
      `<script src="https://api.hostingguard.lat/pixel.js?id=${siteId}"></script>`
    );
    setCopiedSiteId(siteId);
    setTimeout(() => setCopiedSiteId(null), 2000);
  }, []);

  return {
    // Site list
    sites, sitesLoading, selectedSite, setSelectedSite,
    // Period
    days, setDays,
    // Chart data
    stats, timeseries, devices, countries, pages, chartsLoading,
    // Admin
    adminStats, adminOverview, adminEvents,
    // Actions
    createSite, deleteSite, copySnippet, copiedSiteId,
  };
}
