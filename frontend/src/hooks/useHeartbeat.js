import { useEffect, useRef } from 'react';
import { sendHeartbeat } from '../services/api';

const INTERVAL_MS = 60_000;
const DEBOUNCE_MS = 2_000; // avoid rapid-fire on fast navigation

export function useHeartbeat(path = '/') {
  const pathRef    = useRef(path);
  const timerRef   = useRef(null);
  const lastSent   = useRef(0);

  useEffect(() => { pathRef.current = path; }, [path]);

  // Fire immediately on path change (debounced)
  useEffect(() => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      sendHeartbeat(pathRef.current);
      lastSent.current = Date.now();
    }, DEBOUNCE_MS);
    return () => clearTimeout(timerRef.current);
  }, [path]);

  useEffect(() => {
    // Initial heartbeat on mount
    sendHeartbeat(pathRef.current);
    lastSent.current = Date.now();

    // Periodic interval
    const id = setInterval(() => {
      sendHeartbeat(pathRef.current);
      lastSent.current = Date.now();
    }, INTERVAL_MS);

    // Tab becomes visible again
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        const gap = Date.now() - lastSent.current;
        if (gap > 30_000) {
          sendHeartbeat(pathRef.current);
          lastSent.current = Date.now();
        }
      }
    };

    // Window regains focus
    const onFocus = () => {
      const gap = Date.now() - lastSent.current;
      if (gap > 30_000) {
        sendHeartbeat(pathRef.current);
        lastSent.current = Date.now();
      }
    };

    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onFocus);

    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onFocus);
    };
  }, []);
}
