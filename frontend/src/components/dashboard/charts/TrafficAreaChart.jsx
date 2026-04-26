import { AreaChart, Area, XAxis, Tooltip, ResponsiveContainer, YAxis, CartesianGrid } from 'recharts';

export default function TrafficAreaChart({ data }) {
  if (!data || data.length < 2) {
    return <div className="h-[240px] bg-[#121214] border border-white/8 rounded-xl animate-pulse" />;
  }

  const chartData = data.map((d, i) => ({
    name: d.date ? d.date.slice(5) : `Día ${i + 1}`,
    'Visitas': d.page_views || 0,
    'Sesiones': d.unique_sessions || 0,
  }));

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
      <div style={{ background: '#1a1a1f', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '10px 14px', fontSize: 12 }}>
        <div style={{ color: '#888', marginBottom: 6, fontSize: 11 }}>{label}</div>
        {payload.map(p => (
          <div key={p.name} style={{ color: p.color, fontWeight: 700 }}>{p.name}: {p.value}</div>
        ))}
      </div>
    );
  };

  return (
    <div style={{ background: '#121214', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, padding: '20px 20px 12px', overflow: 'hidden' }}>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', marginBottom: 2 }}>Tráfico del sitio</div>
        <div style={{ fontSize: 11, color: '#555' }}>Vistas de página y sesiones únicas</div>
      </div>
      <div style={{ height: 200 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
            <defs>
              <linearGradient id="gViews" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gSessions" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#818cf8" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.04)" />
            <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#555', fontSize: 10 }} dy={8} />
            <YAxis axisLine={false} tickLine={false} tick={{ fill: '#555', fontSize: 10 }} />
            <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'rgba(255,255,255,0.06)', strokeWidth: 1 }} />
            <Area type="monotone" dataKey="Visitas" stroke="#3b82f6" strokeWidth={2} fill="url(#gViews)" dot={false} />
            <Area type="monotone" dataKey="Sesiones" stroke="#818cf8" strokeWidth={1.5} fill="url(#gSessions)" dot={false} strokeDasharray="4 2" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div style={{ display: 'flex', gap: 16, marginTop: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 12, height: 2, background: '#3b82f6', borderRadius: 1 }} />
          <span style={{ fontSize: 10, color: '#555' }}>Visitas</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 12, height: 2, background: '#818cf8', borderRadius: 1 }} />
          <span style={{ fontSize: 10, color: '#555' }}>Sesiones</span>
        </div>
      </div>
    </div>
  );
}
