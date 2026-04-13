import { AreaChart, Area, XAxis, Tooltip, ResponsiveContainer, YAxis, CartesianGrid } from 'recharts';

export default function TrafficAreaChart({ data }) {
  if (!data || data.length < 2) {
    return <div className="h-[250px] bg-[#0d1117] border border-white/10 rounded-xl animate-pulse" />;
  }

  // Pre-process data specifically for the Area Chart if needed
  const chartData = data.map((d, i) => ({
    name: d.date || `Dia ${i + 1}`,
    page_views: d.page_views || 0,
    sessions: d.unique_sessions || 0,
  }));

  return (
    <div className="bg-[#0d1117] border border-[#2b3245] rounded-xl p-5 shadow-2xl overflow-hidden relative">
      <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-emerald-400 to-cyan-500"></div>
      
      <div className="mb-4">
        <h3 className="text-[12px] font-mono text-cyan-400 uppercase tracking-widest font-bold">Rendimiento de Tráfico</h3>
        <p className="text-[10px] text-gray-500">Visualización de Vistas de Página a lo largo del tiempo</p>
      </div>

      <div className="h-[200px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="colorViews" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.6}/>
                <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#ffffff0a" />
            <XAxis 
              dataKey="name" 
              axisLine={false} 
              tickLine={false} 
              tick={{ fill: '#8b949e', fontSize: 10 }}
              dy={10}
            />
            <YAxis 
              axisLine={false} 
              tickLine={false} 
              tick={{ fill: '#8b949e', fontSize: 10 }}
            />
            <Tooltip 
              contentStyle={{ backgroundColor: '#161b22', borderColor: '#30363d', borderRadius: '8px', color: '#fff', fontSize: '11px' }}
              itemStyle={{ color: '#fff', fontWeight: 'bold' }}
              cursor={{ fill: 'rgba(255, 255, 255, 0.02)' }}
            />
            <Area 
              type="monotone" 
              dataKey="page_views" 
              name="Visitas"
              stroke="#10b981" 
              strokeWidth={3}
              fillOpacity={1} 
              fill="url(#colorViews)" 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
