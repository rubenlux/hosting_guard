import { useEffect, useRef } from 'react';

/**
 * Runs `callback` immediately, then every `interval` milliseconds.
 * Stops automatically on unmount or when `enabled` becomes false.
 *
 * Uses a ref so changing `callback` identity never restarts the timer —
 * the latest version is always called without triggering a new setInterval.
 *
 * @param {() => void} callback  - function to run (can be async; errors are not caught here)
 * @param {number}     interval  - milliseconds between calls
 * @param {boolean}    [enabled] - set to false to pause polling (default: true)
 */
export function usePolling(callback, interval, enabled = true) {
  const callbackRef = useRef(callback);

  // Keep ref in sync with latest callback without re-running the effect.
  useEffect(() => {
    callbackRef.current = callback;
  });

  useEffect(() => {
    if (!enabled) return;

    callbackRef.current();                          // run immediately
    const id = setInterval(() => callbackRef.current(), interval);
    return () => clearInterval(id);
  }, [interval, enabled]);
}
