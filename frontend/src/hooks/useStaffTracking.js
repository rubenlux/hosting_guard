/**
 * useStaffTracking
 *
 * Hook para trackear actividad de colaboradores en background.
 * Se llama desde cualquier componente del staff dashboard:
 *
 *   const { track } = useStaffTracking();
 *   track('hosting_viewed', { target_hosting_id: 5, target_user_id: 12 });
 *
 * - El POST es fire-and-forget: nunca bloquea la UI.
 * - Si falla, encola el evento y reintenta automáticamente (máx 20 eventos en cola).
 * - El colaborador no ve nada de este tracking.
 */
import { useCallback, useEffect, useRef } from 'react';
import { trackActivity } from '../services/api';

const MAX_QUEUE = 20;
const RETRY_INTERVAL_MS = 30_000; // reintentar cola cada 30s

export function useStaffTracking() {
  const queue = useRef([]);   // eventos pendientes de reintento
  const timer = useRef(null);

  // Drena la cola en background
  const drainQueue = useCallback(async () => {
    if (queue.current.length === 0) return;
    const pending = [...queue.current];
    queue.current = [];
    for (const event of pending) {
      try {
        await trackActivity(event);
      } catch {
        // Reencolar si sigue fallando, respetando el límite
        if (queue.current.length < MAX_QUEUE) {
          queue.current.push(event);
        }
      }
    }
  }, []);

  // Reintentar cola periódicamente
  useEffect(() => {
    timer.current = setInterval(drainQueue, RETRY_INTERVAL_MS);
    return () => clearInterval(timer.current);
  }, [drainQueue]);

  /**
   * track(actionType, meta?)
   *
   * @param {string} actionType  - Tipo de evento (ver VALID_ACTION_TYPES en backend)
   * @param {object} [meta]      - Datos opcionales: target_user_id, target_hosting_id,
   *                               duration_seconds, description
   */
  const track = useCallback(async (actionType, meta = {}) => {
    const event = {
      action_type:       actionType,
      description:       meta.description || actionType.replace(/_/g, ' '),
      target_user_id:    meta.target_user_id    ?? null,
      target_hosting_id: meta.target_hosting_id ?? null,
      duration_seconds:  meta.duration_seconds  ?? null,
    };

    try {
      await trackActivity(event);
    } catch {
      // Si falla, encolar para reintento posterior
      if (queue.current.length < MAX_QUEUE) {
        queue.current.push(event);
      }
    }
  }, []);

  /**
   * trackTimed(actionType, meta?)
   *
   * Devuelve una función `stop()` que, al llamarse, registra el evento
   * con la duración real transcurrida.
   *
   *   const stop = trackTimed('hosting_viewed', { target_hosting_id: 5 });
   *   // ... el usuario ve el hosting ...
   *   stop(); // registra el evento con duration_seconds calculado
   */
  const trackTimed = useCallback((actionType, meta = {}) => {
    const start = Date.now();
    return () => {
      const duration_seconds = Math.round((Date.now() - start) / 1000);
      track(actionType, { ...meta, duration_seconds });
    };
  }, [track]);

  return { track, trackTimed };
}
