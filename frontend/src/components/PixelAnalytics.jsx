import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus, Trash2, Copy, CheckCircle, BarChart3, Globe, Users, Clock, Monitor, X } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

export default function PixelAnalytics() {
  const { user } = useAuth();
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSite, setSelectedSite] = useState(null);
  const [stats, setStats] = useState(null);
  const [adminStats, setAdminStats] = useState(null);
  
  // Create Site form
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDomain, setNewDomain] = useState('');
  const [creating, setCreating] = useState(false);
  const [copiedScript, setCopiedScript] = useState(null);

  const fetchSites = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/pixel/sites');
      setSites(data);
      if (data.length > 0 && !selectedSite) {
        setSelectedSite(data[0]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchAdminStats = async () => {
    if (user?.role !== 'admin') return;
    try {
      const { data } = await api.get('/pixel/admin/stats');
      setAdminStats(data);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchSiteStats = async (siteId) => {
    try {
      const { data } = await api.get(`/pixel/sites/${siteId}/stats`);
      setStats(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchSites();
    fetchAdminStats();
  }, []);

  useEffect(() => {
    if (selectedSite) {
      fetchSiteStats(selectedSite.site_id);
      const interval = setInterval(() => fetchSiteStats(selectedSite.site_id), 15000);
      return () => clearInterval(interval);
    }
  }, [selectedSite]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post('/pixel/sites', { name: newName, domain: newDomain });
      setShowCreate(false);
      setNewName('');
      setNewDomain('');
      fetchSites();
    } catch (err) {
      console.error(err);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (siteId) => {
    if (!confirm('¿Seguro que quieres eliminar este sitio web y TODOS sus datos analíticos?')) return;
    try {
      await api.delete(`/pixel/sites/${siteId}`);
      if (selectedSite?.site_id === siteId) {
        setSelectedSite(null);
        setStats(null);
      }
      fetchSites();
    } catch (err) {
      console.error(err);
    }
  };

  const copySnippet = (siteId) => {
    const snippet = `<script src="https://api.hostingguard.lat/pixel.js?id=${siteId}"></script>`;
    navigator.clipboard.writeText(snippet);
    setCopiedScript(siteId);
    setTimeout(() => setCopiedScript(null), 2000);
  };

  return (
    <div className="flex flex-col gap-6">
      
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-accent" /> Pixel Analytics Server
          </h2>
          <p className="text-sm text-gray-400">Rastrea visitas y eventos en cualquier página web (interna o externa).</p>
        </div>
        <button 
          onClick={() => setShowCreate(!showCreate)}
          className="btn-dash btn-primary-dash text-sm font-bold flex items-center gap-2"
        >
          {showCreate ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          {showCreate ? "Cancelar" : "Registrar Sitio"}
        </button>
      </div>

      {/* Admin Panel */}
      {adminStats && (
        <div className="p-4 bg-danger/10 border border-danger/30 rounded-2xl border-scanner-warn">
          <div className="text-[10px] text-danger font-mono tracking-widest uppercase mb-2">⚡ GLOBAL ADMIN STATS</div>
          <div className="flex gap-8">
            <div>
              <div className="text-[10px] text-muted font-mono uppercase">Total Pixels Activos</div>
              <div className="font-mono text-glow text-danger text-2xl">{adminStats.total_sites}</div>
            </div>
            <div>
              <div className="text-[10px] text-muted font-mono uppercase">Eventos Recibidos</div>
              <div className="font-mono text-glow text-danger text-2xl">{adminStats.total_events}</div>
            </div>
          </div>
        </div>
      )}

      {/* Create Form */}
      {showCreate && (
        <div className="card-dash p-6 border-scanner">
          <h3 className="text-sm font-bold mb-4">Registrar Nuevo Sitio para Pixel</h3>
          <form onClick={(e) => e.stopPropagation()} onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-mono text-muted mb-1 uppercase">Nombre del Proyecto</label>
                <input 
                  required 
                  value={newName} 
                  onChange={e => setNewName(e.target.value)}
                  className="input-dash bg-[#050505] font-mono text-sm" 
                  placeholder="Ej: Tienda Maria" 
                />
              </div>
              <div>
                <label className="block text-xs font-mono text-muted mb-1 uppercase">Dominio (Opcional)</label>
                <input 
                  value={newDomain} 
                  onChange={e => setNewDomain(e.target.value)}
                  className="input-dash bg-[#050505] font-mono text-sm" 
                  placeholder="Ej: mitienda.com" 
                />
              </div>
            </div>
            <div className="flex justify-end">
              <button disabled={creating} type="submit" className="btn-dash btn-primary-dash">
                {creating ? "Generando..." : "Generar Código Tracker"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Main Layout: Sidebar of Sites + Stats Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        
        {/* Sites List */}
        <div className="lg:col-span-1 space-y-3">
          <div className="text-[10px] font-mono text-muted uppercase tracking-widest pl-2">TUS SITIOS (PIXELS)</div>
          {loading ? (
            <div className="p-4 flex justify-center"><Loader className="w-5 h-5 animate-spin text-accent" /></div>
          ) : sites.length === 0 ? (
            <div className="p-4 text-xs text-muted text-center italic bg-white/5 rounded-xl">Sin pixels registrados</div>
          ) : (
            sites.map(site => (
              <div 
                key={site.site_id}
                onClick={() => setSelectedSite(site)}
                className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${
                  selectedSite?.site_id === site.site_id 
                  ? 'bg-accent/10 border-accent text-white shadow-[0_0_10px_rgba(0,255,136,0.2)]' 
                  : 'bg-[#050505] border-white/5 hover:border-white/20'
                }`}
              >
                <div>
                  <div className="text-sm font-bold flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-accent animate-led"></span>
                    {site.name}
                  </div>
                  <div className="text-[9px] font-mono text-muted mt-1">{site.domain || 'Cualquier dominio'}</div>
                </div>
                <button 
                  onClick={(e) => { e.stopPropagation(); handleDelete(site.site_id); }}
                  className="text-danger/50 hover:text-danger hover:bg-danger/10 p-1.5 rounded-lg"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Stats View */}
        <div className="lg:col-span-3">
          {selectedSite ? (
            <div className="space-y-6">
              
              {/* Snippet Card */}
              <div className="card-dash p-5 bg-[#050505] border-dashed border-white/20">
                <div className="flex justify-between items-start mb-2">
                  <div className="text-xs font-mono uppercase text-accent tracking-widest">Código de Inserción</div>
                  <button 
                    onClick={() => copySnippet(selectedSite.site_id)}
                    className="text-[10px] bg-white/10 hover:bg-white/20 transition-colors px-2 py-1 rounded flex items-center gap-1 font-mono uppercase"
                  >
                    {copiedScript === selectedSite.site_id ? <CheckCircle className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                    {copiedScript === selectedSite.site_id ? 'Copiado!' : 'Copiar'}
                  </button>
                </div>
                <div className="p-3 bg-black rounded-lg border border-white/5 overflow-x-auto text-muted text-xs font-mono whitespace-pre">
                  {`<script src="https://api.hostingguard.lat/pixel.js?id=${selectedSite.site_id}"></script>`}
                </div>
                <div className="text-[10px] text-gray-500 mt-2">Pega esto justo antes de cerrar la etiqueta &lt;/head&gt; de tu sitio web.</div>
              </div>

              {/* Stats Panel */}
              {!stats ? (
                <div className="p-10 flex justify-center"><Loader className="w-6 h-6 animate-spin text-accent" /></div>
              ) : (
                <div className="space-y-6">
                  {/* Top numbers */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {[
                      { title: "Vistas Hoy", val: stats.today_events, icon: <Activity className="w-4 h-4 opacity-50" />, color: "text-[#00ff88]", bc: "border-[#00ff88]/20" },
                      { title: "Eventos Totales", val: stats.total_events, icon: <Database className="w-4 h-4 opacity-50" />, color: "text-[#00aaff]", bc: "border-[#00aaff]/20" },
                      { title: "Sesiones Únicas", val: stats.unique_sessions, icon: <Users className="w-4 h-4 opacity-50" />, color: "text-[#ffaa00]", bc: "border-[#ffaa00]/20" },
                      { title: "Actividad (Últ. Mes)", val: stats.events_by_day?.length || 0, icon: <Clock className="w-4 h-4 opacity-50" />, color: "text-[#aa00ff]", bc: "border-[#aa00ff]/20" }
                    ].map((m, i) => (
                      <div key={i} className={`p-4 bg-[#050505] rounded-xl border ${m.bc} relative overflow-hidden`}>
                        <div className="flex justify-between items-start mb-2">
                          <div className="text-[9px] font-mono tracking-widest uppercase text-muted">{m.title}</div>
                          {m.icon}
                        </div>
                        <div className={`text-2xl font-black font-mono text-glow ${m.color}`}>{m.val}</div>
                      </div>
                    ))}
                  </div>

                  {/* Complex Data */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Top Pages */}
                    <div className="card-dash p-4">
                      <div className="text-xs font-mono font-bold uppercase mb-4 text-white">Top 10 Páginas</div>
                      <div className="space-y-2">
                        {stats.top_pages?.map((p, i) => (
                          <div key={i} className="flex justify-between items-center text-xs border-b border-white/5 pb-2">
                            <div className="truncate pr-4 text-gray-300" title={p.url}>{p.url.replace(/^https?:\/\//,'')}</div>
                            <div className="font-mono text-accent text-glow shrink-0">{p.views} views</div>
                          </div>
                        ))}
                        {(!stats.top_pages || stats.top_pages.length === 0) && <div className="text-[10px] text-muted italic">Sin datos suficientes</div>}
                      </div>
                    </div>

                    {/* Devices & Countries */}
                    <div className="space-y-4">
                      <div className="card-dash p-4">
                        <div className="text-xs font-mono font-bold uppercase mb-3 flex items-center gap-2 text-white">
                          <Monitor className="w-3.5 h-3.5 text-blue-400" /> Por Dispositivo
                        </div>
                        <div className="flex gap-4">
                          {stats.by_device?.map(d => (
                            <div key={d.device} className="bg-white/5 px-3 py-1.5 rounded-lg flex-1 text-center">
                              <div className="text-[10px] uppercase text-muted font-mono">{d.device}</div>
                              <div className="font-mono font-bold text-white text-glow">{d.count}</div>
                            </div>
                          ))}
                          {(!stats.by_device || stats.by_device.length === 0) && <div className="text-[10px] text-muted italic">Sin datos</div>}
                        </div>
                      </div>
                      <div className="card-dash p-4">
                        <div className="text-xs font-mono font-bold uppercase mb-3 flex items-center gap-2 text-white">
                          <Globe className="w-3.5 h-3.5 text-purple-400" /> Por País (IP)
                        </div>
                        <div className="space-y-2">
                          {stats.by_country?.map(c => (
                            <div key={c.country} className="flex justify-between items-center text-xs">
                              <span className="text-gray-300">{c.country}</span>
                              <span className="font-mono text-muted">{c.count}</span>
                            </div>
                          ))}
                          {(!stats.by_country || stats.by_country.length === 0) && <div className="text-[10px] text-muted italic">Requiere GeoIP backend</div>}
                        </div>
                      </div>
                    </div>
                  </div>
                  
                </div>
              )}
            </div>
          ) : (
            <div className="h-full min-h-[300px] flex items-center justify-center border border-dashed border-white/10 rounded-2xl">
              <div className="text-center text-muted">
                <BarChart3 className="w-8 h-8 opacity-20 mx-auto mb-2" />
                <div className="text-sm font-mono">Selecciona un sitio para ver el tráfico</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
