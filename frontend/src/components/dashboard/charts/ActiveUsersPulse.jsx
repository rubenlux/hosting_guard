import { Activity, Radio } from 'lucide-react';

export default function ActiveUsersPulse({ active = 0 }) {
  const isLive = active > 0;

  return (
    <div className="bg-[#0d1117] border border-[#2b3245] rounded-xl p-6 shadow-2xl relative flex flex-col items-center justify-center min-h-[190px]">
      <div className="absolute top-4 left-4 flex items-center gap-2">
        <Radio className={`w-4 h-4 ${isLive ? 'text-green-500 animate-pulse' : 'text-gray-500'}`} />
        <h3 className={`text-[12px] font-mono uppercase tracking-widest font-bold ${isLive ? 'text-green-400' : 'text-gray-500'}`}>
          Tiempo Real
        </h3>
      </div>

      <div className="relative mt-4">
        {/* Animated rings for live effect */}
        {isLive && (
          <>
            <div className="absolute inset-0 bg-green-500/20 rounded-full blur-xl scale-150 animate-pulse"></div>
            <div className="absolute inset-0 border border-green-500/30 rounded-full scale-[2.0] animate-ping opacity-20"></div>
          </>
        )}
        
        {/* Core display */}
        <div className={`relative z-10 flex flex-col items-center justify-center w-28 h-28 rounded-full border-4 ${isLive ? 'border-green-500/80 bg-[#0d1117]' : 'border-gray-800 bg-[#050505] shadow-inner'}`}>
          <span className={`text-4xl font-black ${isLive ? 'text-white' : 'text-gray-600'}`}>{active}</span>
          <span className="text-[9px] text-gray-500 uppercase tracking-widest mt-1">Activos</span>
        </div>
      </div>
    </div>
  );
}
