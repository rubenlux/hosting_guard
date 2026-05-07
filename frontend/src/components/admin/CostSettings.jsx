import React, { useEffect, useState, useCallback } from 'react';
import { Settings, RefreshCw, Save, AlertTriangle, CheckCircle2, Server } from 'lucide-react';
import { getCostSettings, updateCostSettings } from '../../services/api';

const FIELD_GROUPS = [
  {
    title: 'Servidor',
    fields: [
      { key: 'monthly_server_cost_usd', label: 'Costo servidor/mes', unit: '$', step: '0.01', min: 0 },
      { key: 'total_vcpu',              label: 'vCPU disponibles',   unit: 'vCPU', step: '0.5', min: 0.5 },
      { key: 'total_ram_gb',            label: 'RAM disponible',     unit: 'GB',  step: '0.5', min: 0.5 },
      { key: 'total_disk_gb',           label: 'Disco disponible',   unit: 'GB',  step: '1',   min: 1   },
      { key: 'target_utilization_percent', label: 'Utilización objetivo', unit: '%', step: '5', min: 10, max: 100 },
    ],
  },
  {
    title: 'Ponderación de recursos',
    note: 'Deben sumar 1.00',
    fields: [
      { key: 'cpu_cost_weight',      label: 'Peso CPU',       unit: '', step: '0.01', min: 0, max: 1 },
      { key: 'ram_cost_weight',      label: 'Peso RAM',       unit: '', step: '0.01', min: 0, max: 1 },
      { key: 'disk_cost_weight',     label: 'Peso Disco',     unit: '', step: '0.01', min: 0, max: 1 },
      { key: 'overhead_cost_weight', label: 'Peso Overhead',  unit: '', step: '0.01', min: 0, max: 1 },
    ],
  },
  {
    title: 'Costos variables',
    fields: [
      { key: 'backup_cost_per_gb_month_usd',  label: 'Backup ($/GB/mes)',    unit: '$',  step: '0.001', min: 0 },
      { key: 'ai_cost_per_query_usd',         label: 'IA ($/query)',          unit: '$',  step: '0.001', min: 0 },
      { key: 'human_support_hourly_cost_usd', label: 'Soporte humano ($/h)', unit: '$',  step: '0.5',   min: 0 },
    ],
  },
  {
    title: 'Comisión de pago',
    fields: [
      { key: 'payment_fee_percent',  label: 'Comisión %',      unit: '%', step: '0.1', min: 0 },
      { key: 'payment_fee_fixed_usd', label: 'Comisión fija', unit: '$', step: '0.01', min: 0 },
    ],
  },
];

function fmtVal(v) {
  if (v == null) return '';
  return String(v);
}

export default function CostSettings() {
  const [data,    setData]    = useState(null);
  const [form,    setForm]    = useState({});
  const [loading, setLoading] = useState(true);
  const [saving,  setSaving]  = useState(false);
  const [error,   setError]   = useState(null);
  const [success, setSuccess] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getCostSettings();
      setData(d);
      const init = {};
      FIELD_GROUPS.forEach(g => g.fields.forEach(f => {
        init[f.key] = fmtVal(d[f.key]);
      }));
      setForm(init);
    } catch {
      setError('Error cargando configuración');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const weightSum = () => {
    const keys = ['cpu_cost_weight', 'ram_cost_weight', 'disk_cost_weight', 'overhead_cost_weight'];
    return keys.reduce((s, k) => s + (parseFloat(form[k]) || 0), 0);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const patch = {};
      FIELD_GROUPS.forEach(g => g.fields.forEach(f => {
        const raw = form[f.key];
        if (raw !== '' && raw != null) {
          const num = parseFloat(raw);
          if (!isNaN(num) && String(num) !== fmtVal(data?.[f.key])) {
            patch[f.key] = num;
          }
        }
      }));
      if (Object.keys(patch).length === 0) {
        setSaving(false);
        return;
      }
      const updated = await updateCostSettings(patch);
      setData(updated);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error guardando configuración');
    } finally {
      setSaving(false);
    }
  };

  const ws = weightSum();
  const weightOk = Math.abs(ws - 1) < 0.011;

  return (
    <div className="bg-[#111] rounded-xl border border-white/8 overflow-hidden">
      <div className="px-4 py-3 border-b border-white/5 flex items-center gap-2">
        <Server className="w-3.5 h-3.5 text-blue-400" />
        <span className="text-[11px] font-semibold text-white">Configuración de Costos</span>
        <span className="ml-auto text-[9px] text-gray-600">cost_settings</span>
        <button onClick={load} disabled={loading} className="p-1 rounded hover:bg-white/5 transition-colors">
          <RefreshCw className={`w-3 h-3 text-gray-500 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="mx-4 mt-3 flex items-center gap-2 text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {error}
        </div>
      )}
      {success && (
        <div className="mx-4 mt-3 flex items-center gap-2 text-[11px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2">
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> Configuración guardada
        </div>
      )}

      {!loading && (
        <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-6">
          {FIELD_GROUPS.map((group) => (
            <div key={group.title}>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wide">{group.title}</span>
                {group.note && (
                  <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${weightOk ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'}`}>
                    {group.note} — actual: {ws.toFixed(2)}
                  </span>
                )}
              </div>
              <div className="flex flex-col gap-2">
                {group.fields.map((f) => (
                  <div key={f.key} className="flex items-center gap-2">
                    <label className="text-[10px] text-gray-500 w-44 shrink-0">{f.label}</label>
                    <div className="flex items-center gap-1 flex-1">
                      <input
                        type="number"
                        step={f.step}
                        min={f.min}
                        max={f.max}
                        value={form[f.key] ?? ''}
                        onChange={(e) => setForm(prev => ({ ...prev, [f.key]: e.target.value }))}
                        className="w-full bg-[#0d0d0f] border border-white/10 rounded-lg px-2 py-1.5 text-[11px] text-white font-mono focus:outline-none focus:border-blue-500/50 transition-colors"
                      />
                      {f.unit && <span className="text-[10px] text-gray-600 shrink-0 w-8">{f.unit}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && (
        <div className="px-4 pb-4 flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving || !weightOk}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-[11px] font-bold bg-blue-500/15 text-blue-400 border border-blue-500/20 hover:bg-blue-500/25 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? 'Guardando...' : 'Guardar cambios'}
          </button>
        </div>
      )}
    </div>
  );
}
