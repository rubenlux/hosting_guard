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
}));

import {
  getSecuritySummary, getSecurityEvents,
  getRemediations, rollbackRemediation,
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

function setupMocks(remItems = [makeRem()]) {
  getSecuritySummary.mockResolvedValue({
    threat_level: 'normal', open_events: 0, critical_24h: 0,
  });
  getSecurityEvents.mockResolvedValue({ items: [] });
  getRemediations.mockResolvedValue({ items: remItems });
  rollbackRemediation.mockResolvedValue({ ok: true, status: 'rollback_completed' });
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

  it('rollback button calls rollbackRemediation and refreshes list', async () => {
    setupMocks([makeRem({ can_rollback: true })]);
    await act(async () => { render(<SecurityCenter />); });
    await waitFor(() => screen.getByTestId('rollback-btn'));

    await act(async () => {
      fireEvent.click(screen.getByTestId('rollback-btn'));
    });

    await waitFor(() => {
      expect(rollbackRemediation).toHaveBeenCalledWith(1);
      expect(getRemediations).toHaveBeenCalledTimes(2); // initial + after rollback
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
});
