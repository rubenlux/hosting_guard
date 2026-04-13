import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function SessionsBarChart({ data }) {
  if (!data || data.length < 2) return null;

  const chartData = data.map((d, i) => ({
    name: d.date || `Dia ${i + 1}`,
    sessions: d.unique_sessions || 0,
  }));

  return (
    <div className="bg-[#0d1117] border border-[#2b3245] rounded-xl p-5 shadow-2xl overflow-hidden">
      <div className="mb-4">
        <h3 className="text-[12px] font-mono text-purple-400 uppercase tracking-widest font-bold">Distribución de Sesiones</h3>
      </div>
      <div className="h-[140px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <XAxis dataKey="name" hide />
            <Tooltip 
              contentStyle={{ backgroundColor: '#161b22', borderColor: '#30363d', borderRadius: '8px', fontSize: '10px' }}
              itemStyle={{ color: '#a78bfa', fontWeight: 'bold' }}
              cursor={{ fill: 'rgba(167, 139, 250, 0.05)' }}
            />
            <Bar dataKey="sessions" fill="#8b5cf6" radius={[4, 4, 0, 0]} barSize={8} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
