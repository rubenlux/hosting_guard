import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

export default function SessionsBarChart({ data }) {
  if (!data || data.length < 2) return null;

  const chartData = data.map((d, i) => ({
    name: d.date ? d.date.slice(5) : `D${i + 1}`,
    sesiones: d.unique_sessions || 0,
  }));

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
      <div style={{ background: '#1a1a1f', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '8px 12px', fontSize: 11 }}>
        <div style={{ color: '#888', marginBottom: 4 }}>{label}</div>
        <div style={{ color: '#3b82f6', fontWeight: 700 }}>{payload[0].value} sesiones</div>
      </div>
    );
  };

  return (
    <div style={{ background: '#121214', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, padding: '16px 16px 10px', overflow: 'hidden' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#fff', marginBottom: 12 }}>Sesiones por día</div>
      <div style={{ height: 80 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} strokeDasharray="2 2" stroke="rgba(255,255,255,0.04)" />
            <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#555', fontSize: 9 }} />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(59,130,246,0.05)' }} />
            <Bar dataKey="sesiones" fill="#3b82f6" radius={[3, 3, 0, 0]} barSize={10} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
