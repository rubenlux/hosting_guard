/**
 * SecurityCenter — Remediaciones automáticas section tests.
 *
 * Covers:
 * 1. RemediationsSection renders on mount.
 * 2. Shows remediation rows from API.
 * 3. Status badge uses status_label.
 * 4. Rollback button visible for can_rollback=true.
 * 5. Rollback button absent for can_rollback=false.
 * 6. Rollback button calls rollbackRemediation and refreshes.
 * 7. Error shown on load failure.
 * 8. Empty state shown when no items.
 * 9. Status filter changes trigger reload.
 * 10. Refresh button triggers reload.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../../services/api', () => ({
  getSecuritySummary:        vi.fn(),
  getSecurityEvents:         vi.fn(),
  resolveSecurityEvent:      vi.fn(),
  getSecurityEventAISummary: vi.fn(),
  getRemediations:           vi.fn(),
  rollbackRemediation:       vi.fn(),
  getAdminHostings:          vi.fn(),
  getProtectionMode:         vi.fn(),
  putProtectionMode:         vi.fn(),
}));

import {
  getSecuritySummary, getSecurityEvents,
  getRemediations, rollbackRemediation,
  getAdminHostings, getProtectionMode, putProtectionMode,
} from '../../services/api';
import SecurityCenter from './SecurityCenter';

// ── helpers ───────────────────────────────────────────────────────────────────

function makeRem(overrides = {}) {
  return {
    remediation_id: 1,
    hosting_id: 5,
    remediation_type: 'temporary_ip_block',
    type_label: 'Bloqueo IP temporal',
    rule_id: 'wp_login_brute_force',
    target_type: 'ip',
    target_value: '1.2.3.4',
    status: 'applied',
    status_label: 'Aplicado',
    can_rollback: true,
    is_active: true,
    risk_level: 'medium',
    reason: 'brute_force_wp_login',
    ttl_seconds: 900,
    expires_at: null,
    created_at: '2026-05-13T10:00:00Z',
    ...overrides,
  };
}

const MOCK_HOSTINGS = [
  { hosting_id: 5, name: 'Mi Sitio', subdomain: 'misitio.hostingguard.lat' },
  { hosting_id: 6, name: 'Otro Sitio', subdomain: 'otro.hostingguard.lat' },
];

function setupMocks(remItems = [makeRem()]) {
  getSecuritySummary.mockResolvedValue({
    threat_level: 'normal', open_events: 0, critical_24h: 0,
  });
  getSecurityEvents.mockResolvedValue({ items: [] });
  getRemediations.mockResolvedValue({ items: remItems });
  rollbackRemediation.mockResolvedValue({ ok: true, status: 'rollback_completed' });
  getAdminHostings.mockResolvedValue(MOCK_HOSTINGS);
  getProtectionMode.mockResolvedValue({ hosting_id: 5, mode: 'monitor', protection_mode: { enabled: true } });
  putProtectionMode.mockResolvedValue({ ok: true, mode: 'protect' });
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe('SecurityCenter — RemediationsSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders remediations section on mount', async () => {
    setupMocks();
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => {
      expect(screen.getByTestId('remediations-section')).toBeTruthy();
    });
    expect(getRemediations).toHaveBeenCalledTimes(1);
  });

  it('shows remediation rows from API', async () => {
    setupMocks([makeRem(), makeRem({ remediation_id: 2, target_value: '9.8.7.6' })]);
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => {
      const rows = screen.getAllByTestId('remediation-row');
      expect(rows.length).toBe(2);
    });
  });

  it('status badge displays status_label', async () => {
    setupMocks([makeRem({ status: 'applied', status_label: 'Aplicado' })]);
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => {
      expect(screen.getByTestId('rem-status-badge')).toBeTruthy();
      expect(screen.getByTestId('rem-status-badge').textContent).toBe('Aplicado');
    });
  });

  it('rollback button visible when can_rollback=true', async () => {
    setupMocks([makeRem({ can_rollback: true })]);
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => {
      expect(screen.getByTestId('rollback-btn')).toBeTruthy();
    });
  });

  it('rollback button absent when can_rollback=false', async () => {
    setupMocks([makeRem({ can_rollback: false, status: 'blocked_by_policy', status_label: 'Bloqueado' })]);
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => {
      expect(screen.queryByTestId('rollback-btn')).toBeNull();
    });
  });

  it('rollback button calls rollbackRemediation and refreshes list after confirm', async () => {
    setupMocks([makeRem({ can_rollback: true })]);
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('rollback-btn'));

    await act(async () => { fireEvent.click(screen.getByTestId('rollback-btn')); });
    await waitFor(() => screen.getByTestId('rollback-confirm-btn'));

    await act(async () => { fireEvent.click(screen.getByTestId('rollback-confirm-btn')); });

    await waitFor(() => {
      expect(rollbackRemediation).toHaveBeenCalledWith(1);
      expect(getRemediations).toHaveBeenCalledTimes(2);
    });
  });

  it('empty state shown when no items', async () => {
    setupMocks([]);
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => {
      expect(screen.getByText(/No hay remediaciones registradas/i)).toBeTruthy();
    });
  });

  it('error shown on load failure', async () => {
    getSecuritySummary.mockResolvedValue({ threat_level: 'normal', open_events: 0, critical_24h: 0 });
    getSecurityEvents.mockResolvedValue({ items: [] });
    getRemediations.mockRejectedValue(new Error('Network error'));
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => {
      expect(screen.getByText(/Error cargando remediaciones/i)).toBeTruthy();
    });
  });

  it('status filter change triggers reload', async () => {
    setupMocks();
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('rem-status-filter'));

    await act(async () => {
      fireEvent.change(screen.getByTestId('rem-status-filter'), { target: { value: 'rollback_completed' } });
    });

    await waitFor(() => {
      expect(getRemediations).toHaveBeenCalledTimes(2);
      const lastCall = getRemediations.mock.calls[1][0];
      expect(lastCall.status).toBe('rollback_completed');
    });
  });

  it('rollback button shows "Revertir bloqueo" text', async () => {
    setupMocks([makeRem({ can_rollback: true })]);
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => {
      expect(screen.getByTestId('rollback-btn').textContent).toContain('Revertir bloqueo');
    });
  });

  it('clicking rollback opens confirmation dialog', async () => {
    setupMocks([makeRem({ can_rollback: true })]);
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('rollback-btn'));

    await act(async () => { fireEvent.click(screen.getByTestId('rollback-btn')); });

    await waitFor(() => {
      expect(screen.getByTestId('rollback-confirm-dialog')).toBeTruthy();
    });
  });

  it('cancel in confirmation dialog dismisses without calling rollbackRemediation', async () => {
    setupMocks([makeRem({ can_rollback: true })]);
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('rollback-btn'));

    await act(async () => { fireEvent.click(screen.getByTestId('rollback-btn')); });
    await waitFor(() => screen.getByTestId('rollback-cancel-btn'));

    await act(async () => { fireEvent.click(screen.getByTestId('rollback-cancel-btn')); });

    await waitFor(() => {
      expect(rollbackRemediation).not.toHaveBeenCalled();
      expect(screen.queryByTestId('rollback-confirm-dialog')).toBeNull();
    });
  });

  it('confirming rollback shows success toast', async () => {
    setupMocks([makeRem({ can_rollback: true })]);
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('rollback-btn'));

    await act(async () => { fireEvent.click(screen.getByTestId('rollback-btn')); });
    await waitFor(() => screen.getByTestId('rollback-confirm-btn'));

    await act(async () => { fireEvent.click(screen.getByTestId('rollback-confirm-btn')); });

    await waitFor(() => {
      expect(screen.getByTestId('rollback-toast')).toBeTruthy();
      expect(screen.getByTestId('rollback-toast').textContent).toContain('revertido');
    });
  });
});

// ── ProtectionModePanel tests ─────────────────────────────────────────────────

describe('SecurityCenter — ProtectionModePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders protection mode panel', async () => {
    setupMocks();
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => {
      expect(screen.getByTestId('protection-mode-panel')).toBeTruthy();
    });
  });

  it('loads hostings into selector on mount', async () => {
    setupMocks();
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => {
      expect(getAdminHostings).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId('hosting-select')).toBeTruthy();
    });
  });

  it('loads current mode when hosting is selected', async () => {
    setupMocks();
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => {
      expect(getProtectionMode).toHaveBeenCalledWith(5);
    });
  });

  it('mode selector shows three options: off, monitor, protect', async () => {
    setupMocks();
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('mode-selector'));

    expect(screen.getByTestId('mode-btn-off')).toBeTruthy();
    expect(screen.getByTestId('mode-btn-monitor')).toBeTruthy();
    expect(screen.getByTestId('mode-btn-protect')).toBeTruthy();
  });

  it('clicking a mode button changes selection', async () => {
    setupMocks();
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('mode-btn-protect'));

    await act(async () => { fireEvent.click(screen.getByTestId('mode-btn-protect')); });

    await waitFor(() => {
      expect(screen.getByTestId('protect-warning')).toBeTruthy();
    });
  });

  it('protect warning shown only when protect mode is selected', async () => {
    getProtectionMode.mockResolvedValue({ hosting_id: 5, mode: 'off', protection_mode: {} });
    setupMocks();
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('mode-btn-protect'));

    expect(screen.queryByTestId('protect-warning')).toBeNull();

    await act(async () => { fireEvent.click(screen.getByTestId('mode-btn-protect')); });
    await waitFor(() => {
      expect(screen.getByTestId('protect-warning')).toBeTruthy();
    });
  });

  it('save button calls putProtectionMode with selected hosting and mode', async () => {
    setupMocks();
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('mode-btn-protect'));

    await act(async () => { fireEvent.click(screen.getByTestId('mode-btn-protect')); });
    await act(async () => { fireEvent.click(screen.getByTestId('save-mode-btn')); });

    await waitFor(() => {
      expect(putProtectionMode).toHaveBeenCalledWith(5, 'protect');
    });
  });

  it('success toast shown after successful save', async () => {
    setupMocks();
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('save-mode-btn'));

    await act(async () => { fireEvent.click(screen.getByTestId('save-mode-btn')); });

    await waitFor(() => {
      expect(screen.getByTestId('mode-toast')).toBeTruthy();
      expect(screen.getByTestId('mode-toast').textContent).toContain('actualizado');
    });
  });

  it('error toast shown on save failure', async () => {
    setupMocks();
    putProtectionMode.mockRejectedValueOnce({
      response: { data: { detail: 'Error de prueba' } },
    });
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('save-mode-btn'));

    await act(async () => { fireEvent.click(screen.getByTestId('save-mode-btn')); });

    await waitFor(() => {
      expect(screen.getByTestId('mode-toast')).toBeTruthy();
      expect(screen.getByTestId('mode-toast').textContent).toContain('Error');
    });
  });
});
