import { useState, useRef } from 'react';
import { getLogs } from '../services/api';

/**
 * Manages log fetching state for a hosting container.
 *
 * Supports incremental loading: each refreshLogs() call requests
 * only entries since the last timestamp, then appends to existing log text.
 *
 * Returns:
 *   selectedHosting   — the hosting object currently showing logs (or null)
 *   logs              — string of log content
 *   loading           — true while a fetch is in progress
 *   openLogs(hosting) — start a fresh log session for the given hosting
 *   refreshLogs()     — fetch new log lines since last timestamp
 */
export function useHostingLogs() {
  const [selectedHosting, setSelectedHosting] = useState(null);
  const [logs,            setLogs]            = useState('');
  const [loading,         setLoading]         = useState(false);

  // Timestamp of the last received log chunk — used for incremental fetches.
  // Stored in a ref (not state) so refreshLogs always sees the latest value
  // without the closure going stale between rapid calls.
  const timestampRef = useRef(null);

  async function openLogs(hosting) {
    setSelectedHosting(hosting);
    setLogs('');
    timestampRef.current = null;
    setLoading(true);
    try {
      const data = await getLogs(hosting.hosting_id);
      setLogs(data.logs ?? '');
      timestampRef.current = data.timestamp ?? null;
    } catch {
      setLogs('Error al cargar logs. Inténtalo de nuevo.');
    } finally {
      setLoading(false);
    }
  }

  async function refreshLogs() {
    if (!selectedHosting) return;
    setLoading(true);
    try {
      const data = await getLogs(selectedHosting.hosting_id, timestampRef.current);
      if (data.logs) setLogs(prev => prev + data.logs);
      timestampRef.current = data.timestamp ?? timestampRef.current;
    } catch (err) {
      console.error('[useHostingLogs] refreshLogs failed', err);
    } finally {
      setLoading(false);
    }
  }

  return { selectedHosting, logs, loading, openLogs, refreshLogs };
}
