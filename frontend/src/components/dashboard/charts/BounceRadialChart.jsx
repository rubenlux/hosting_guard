import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';

export default function BounceRadialChart({ bounceRate }) {
  const rate = Math.min(Math.max(bounceRate || 0, 0), 100);
  const data = [
    { name: 'Bounce Rate', value: rate },
    { name: 'Retención', value: 100 - rate }
  ];

  // Dynamic colors based on severity
  const bounceColor = rate > 75 ? '#ef4444' : rate > 40 ? '#f59e0b' : '#3b82f6';
  const COLORS = [bounceColor, '#1b1f28']; // Active and Track

  return (
    <div className="bg-[#0d1117] border border-[#2b3245] rounded-xl pt-5 pb-2 px-5 shadow-2xl relative flex flex-col items-center justify-center">
      
      <div className="w-full mb-1">
        <h3 className="text-[12px] font-mono text-amber-400 uppercase tracking-widest font-bold">Puntuación Bounce</h3>
      </div>

      <div className="h-[140px] w-full relative">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={45}
              outerRadius={65}
              startAngle={180}
              endAngle={-180}
              dataKey="value"
              stroke="none"
              cornerRadius={5}
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip 
              contentStyle={{ backgroundColor: '#161b22', borderColor: '#30363d', borderRadius: '8px', fontSize: '10px' }}
              itemStyle={{ color: '#fff', fontWeight: 'bold' }}
              formatter={(value) => `${value.toFixed(1)}%`}
            />
          </PieChart>
        </ResponsiveContainer>

        {/* Center overlay text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none mt-2">
          <span className="text-2xl font-black text-white">{rate.toFixed(1)}%</span>
          <span className="text-[9px] text-gray-500 uppercase tracking-wider font-mono mt-1">Rebote</span>
        </div>
      </div>
    </div>
  );
}
