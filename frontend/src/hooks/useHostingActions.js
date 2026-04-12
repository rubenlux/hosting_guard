/**
 * Mutation hooks for hosting lifecycle actions.
 * Each mutation invalidates the dashboard query on success so
 * the list refreshes automatically — no manual refresh() call needed.
 *
 * Returns: { start, stop, restart, remove }
 * Each entry is a React Query mutation object with:
 *   .mutate(hostingId)   — fire and forget
 *   .isPending           — loading state
 *   .variables           — the id currently being mutated (useful for per-row spinners)
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { startHosting, stopHosting, restartHosting, deleteHosting } from '../services/api';
import { DASHBOARD_KEY } from './useDashboardData';

function useHostingMutation(mutationFn, errorMsg) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DASHBOARD_KEY, exact: true }),
    onError:   (err) => toast.error(err.response?.data?.detail || errorMsg),
  });
}

export function useHostingActions() {
  const start   = useHostingMutation(startHosting,   'Error al iniciar el hosting');
  const stop    = useHostingMutation(stopHosting,    'Error al detener el hosting');
  const restart = useHostingMutation(restartHosting, 'Error al reiniciar el hosting');
  const remove  = useHostingMutation(deleteHosting,  'Error al eliminar el hosting. Inténtalo de nuevo.');

  return { start, stop, restart, remove };
}
