import { useEffect, useRef } from 'react';
import { sendHeartbeat } from '../services/api';

const INTERVAL_MS = 60_000; // 60 s — matches backend throttle of 25 s

/**
 * Sends a heartbeat to the backend every 60 seconds while the component is mounted.
 * Pass the current path so the admin presence panel can show where each user is.
 */
export function useHeartbeat(path = '/') {
  const pathRef = useRef(path);
  useEffect(() => { pathRef.current = path; }, [path]);

  useEffect(() => {
    sendHeartbeat(pathRef.current);
    const id = setInterval(() => sendHeartbeat(pathRef.current), INTERVAL_MS);
    return () => clearInterval(id);
  }, []); // mount once; path changes are picked up via ref
}
