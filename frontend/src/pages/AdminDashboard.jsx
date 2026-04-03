import React, { useEffect, useState } from 'react';
import { Users, Globe, BarChart3, RefreshCw, ShieldCheck, Activity } from 'lucide-react';
import { getAdminUsers, getAdminHostings, getAdminPixelStats } from '../services/api';

export default function AdminDashboard() {
  const [users, setUsers]         = useState([]);
  const [hostings, setHostings]   = useState([]);
  const [pixelStats, setPixelStats] = useState(null);
  const [loading, setLoading]     = useState(true);
  const [activeTab, setActiveTab] = useState('users');

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [u, h, p] = await Promise.all([
        getAdminUsers(),
        getAdminHostings(),
        getAdminPixelStats(),
      ]);
      setUsers(u);
      setHostings(h);
      setPixelStats(p);
    } catch (err) {
      console.error('Admin fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const planColor = {
    free:     'text-muted bg-white/5',
    personal: 'text-[#00aaff] bg-[#00aaff]/10',
    negocio:  'text-[#ffaa00] bg-[#ffaa00]/10',
    agencia:  'text-[#aa00ff] bg-[#aa00ff]/10',
  };

  const statusColor = {
    active:   'text-[#00ff88]',
    stopped:  'text-danger',
    expired:  'text-red-600',
    error:    'text-danger',
    starting: 'text-[#ffaa00]',
  };

  return (
    <div className="flex flex-col gap-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-danger" /> Panel de Administración
          </h2>
          <p className="text-sm text-gray-400">Vista global del sistema — solo admin.</p>
        </div>
        <button onClick={fetchAll} className="btn-dash btn-ghost-dash flex items-center gap-2 text-sm">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Actualizar
        </button>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Usuarios',        val: users.length,                  color: 'text-[#00aaff]', border: 'border-[#00aaff]/20', icon: <Users className="w-4 h-4 opacity-40" /> },
          { label: 'Hostings Totales', val: hostings.length,              color: 'text-[#00ff88]', border: 'border-[#00ff88]/20', icon: <Globe className="w-4 h-4 opacity-40" /> },
          { label: 'Pixels Activos',  val: pixelStats?.total_sites ?? '—', color: 'text-[#ffaa00]', border: 'border-[#ffaa00]/20', icon: <BarChart3 className="w-4 h-4 opacity-40" /> },
          { label: 'Eventos Pixel',   val: pixelStats?.total_events ?? '—', color: 'text-[#aa00ff]', border: 'border-[#aa00ff]/20', icon: <Activity className="w-4 h-4 opacity-40" /> },
        ].map((m, i) => (
          <div key={i} className={`p-4 bg-[#050505] rounded-xl border ${m.border}`}>
            <div className="flex justify-between items-start mb-2">
              <div className="text-[9px] font-mono tracking-widest uppercase text-muted">{m.label}</div>
              {m.icon}
            </div>
            <div className={`text-2xl font-black font-mono text-glow ${m.color}`}>
              {loading ? '…' : m.val}
            </div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/5 pb-1">
        {[
          { id: 'users',    label: `Usuarios (${users.length})` },
          { id: 'hostings', label: `Hostings (${hostings.length})` },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`text-xs font-mono uppercase tracking-widest px-4 py-2 rounded-t-lg transition-all ${
              activeTab === tab.id
                ? 'bg-accent/10 text-accent border-b-2 border-accent'
                : 'text-muted hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Users table */}
      {activeTab === 'users' && (
        <div className="card-dash overflow-x-auto">
          {loading ? (
            <div className="p-10 flex justify-center">
              <RefreshCw className="w-5 h-5 animate-spin text-accent" />
            </div>
          ) : users.length === 0 ? (
            <div className="p-8 text-center text-muted text-sm italic">Sin usuarios registrados.</div>
          ) : (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-white/5 text-muted">
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">ID</th>
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">Email</th>
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">Rol</th>
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">Plan</th>
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">Saldo</th>
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">Creado</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.user_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                    <td className="p-3 text-muted">{u.user_id}</td>
                    <td className="p-3 text-white font-medium">{u.email}</td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase ${
                        u.role === 'admin' ? 'bg-danger/20 text-danger' : 'bg-white/5 text-muted'
                      }`}>
                        {u.role}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase ${planColor[u.plan] || 'text-muted bg-white/5'}`}>
                        {u.plan || 'free'}
                      </span>
                    </td>
                    <td className="p-3 text-accent">${(u.balance || 0).toFixed(2)}</td>
                    <td className="p-3 text-muted">{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Hostings table */}
      {activeTab === 'hostings' && (
        <div className="card-dash overflow-x-auto">
          {loading ? (
            <div className="p-10 flex justify-center">
              <RefreshCw className="w-5 h-5 animate-spin text-accent" />
            </div>
          ) : hostings.length === 0 ? (
            <div className="p-8 text-center text-muted text-sm italic">Sin hostings registrados.</div>
          ) : (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-white/5 text-muted">
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">ID</th>
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">Nombre</th>
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">User ID</th>
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">Plan</th>
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">Estado</th>
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">Subdominio</th>
                  <th className="text-left p-3 font-mono uppercase tracking-widest text-[9px]">Creado</th>
                </tr>
              </thead>
              <tbody>
                {hostings.map(h => (
                  <tr key={h.hosting_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                    <td className="p-3 text-muted">{h.hosting_id}</td>
                    <td className="p-3 text-white font-medium">{h.name}</td>
                    <td className="p-3 text-muted">{h.user_id}</td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase ${planColor[h.plan] || 'text-muted bg-white/5'}`}>
                        {h.plan}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className={`font-bold ${statusColor[h.status] || 'text-muted'}`}>
                        ● {h.status}
                      </span>
                    </td>
                    <td className="p-3 text-muted truncate max-w-[200px]">{h.subdomain}</td>
                    <td className="p-3 text-muted">{h.created_at ? new Date(h.created_at).toLocaleDateString() : '—'}</td>
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
