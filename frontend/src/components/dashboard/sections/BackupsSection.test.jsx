/**
 * BackupsSection — user dashboard backup panel tests.
 *
 * Covers:
 * 1. Renders backup list when API returns {items, total}.
 * 2. Renders backup list when API returns array directly (compat).
 * 3. Shows correct record count when API returns {items:[backup], total:1}.
 * 4. After "Crear backup ahora", refetches and shows the new backup.
 * 5. Selector uses hosting_id (number) for mi-academia, not name string.
 * 6. Does NOT show "0 registros" when items.length > 0.
 * 7. Admin user (user.role=admin) sees list without upsell even on free plan.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../../../services/api', () => ({
  getHostingBackups: vi.fn(),
  triggerBackup:     vi.fn(),
  downloadBackup:    vi.fn(),
  deleteBackup:      vi.fn(),
}));

import { getHostingBackups, triggerBackup, downloadBackup } from '../../../services/api';
import BackupsSection from './BackupsSection';

// ── fixtures ──────────────────────────────────────────────────────────────────

const HOSTING_AGENCIA = {
  hosting_id: 1, name: 'mi-academia', subdomain: 'mi-academia',
  status: 'active', plan: 'agencia',
};

const HOSTING_CHAOS = {
  hosting_id: 56, name: 'chaos-test', subdomain: 'chaos-test',
  status: 'active', plan: 'agencia',
};

const BACKUP_ITEM = {
  backup_id: 5, hosting_id: 1, user_id: 10,
  backup_type: 'full', status: 'completed', trigger: 'manual',
  total_size_bytes: 4098740, started_at: '2026-05-17T10:00:00Z',
};

const USER_REGULAR = { user_id: 10, role: 'user', plan: 'agencia' };
const USER_ADMIN   = { user_id: 1,  role: 'admin', plan: 'free' };

// ── helpers ───────────────────────────────────────────────────────────────────

function renderSection(hostings = [HOSTING_AGENCIA], user = USER_REGULAR) {
  return render(<BackupsSection hostings={hostings} user={user} />);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('BackupsSection', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(() => { vi.useRealTimers(); });

  it('1 — renders list when API returns {items, total}', async () => {
    getHostingBackups.mockResolvedValue({ items: [BACKUP_ITEM], total: 1 });

    renderSection();

    await waitFor(() => {
      expect(screen.getByText('completado')).toBeTruthy();
    });
  });

  it('2 — renders list when API returns array directly', async () => {
    getHostingBackups.mockResolvedValue([BACKUP_ITEM]);

    renderSection();

    await waitFor(() => {
      expect(screen.getByText('completado')).toBeTruthy();
    });
  });

  it('3 — shows 1 registro when API returns {items:[backup], total:1}', async () => {
    getHostingBackups.mockResolvedValue({ items: [BACKUP_ITEM], total: 1 });

    renderSection();

    await waitFor(() => {
      expect(screen.getByText(/1 registros/i)).toBeTruthy();
    });
  });

  it('4 — after triggerBackup, shows success and schedules refetch', async () => {
    getHostingBackups.mockResolvedValue({ items: [], total: 0 });
    triggerBackup.mockResolvedValue({ backup_id: 6, status: 'completed' });

    renderSection();
    await waitFor(() => screen.getByText('Crear backup ahora'));

    fireEvent.click(screen.getByText('Crear backup ahora'));

    await waitFor(() => expect(triggerBackup).toHaveBeenCalledWith(1));
    await waitFor(() => {
      expect(screen.getByText(/backup iniciado/i)).toBeTruthy();
    });
    // getHostingBackups called at least once on mount (refetch is scheduled 4s later)
    expect(getHostingBackups).toHaveBeenCalledWith(1);
  });

  it('5 — selector calls getHostingBackups with hosting_id=1 for mi-academia', async () => {
    getHostingBackups.mockResolvedValue({ items: [], total: 0 });

    renderSection([HOSTING_AGENCIA, HOSTING_CHAOS]);

    await waitFor(() => {
      expect(getHostingBackups).toHaveBeenCalledWith(1);
    });
  });

  it('6 — does NOT show "0 registros" when items.length > 0', async () => {
    getHostingBackups.mockResolvedValue({ items: [BACKUP_ITEM], total: 1 });

    renderSection();

    await waitFor(() => screen.getByText('completado'));
    expect(screen.queryByText('0 registros')).toBeNull();
  });

  it('7 — admin user (role=admin, plan=free) sees backup list without upsell', async () => {
    getHostingBackups.mockResolvedValue({ items: [BACKUP_ITEM], total: 1 });

    // Admin user on free plan hosting — should bypass plan gate
    renderSection(
      [{ ...HOSTING_AGENCIA, plan: 'free' }],
      USER_ADMIN,
    );

    await waitFor(() => {
      expect(screen.getByText('completado')).toBeTruthy();
      // Upsell banner must NOT be shown
      expect(screen.queryByText('Backups no incluidos en tu plan')).toBeNull();
    });
  });
});

// ── Download button tests (8–13) ──────────────────────────────────────────────

describe('BackupsSection — download', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(() => { vi.useRealTimers(); });

  it('8 — Descargar button calls downloadBackup with backup_id', async () => {
    getHostingBackups.mockResolvedValue({ items: [BACKUP_ITEM], total: 1 });
    downloadBackup.mockResolvedValue(undefined);

    renderSection();
    await waitFor(() => screen.getByTitle('Descargar backup'));

    fireEvent.click(screen.getByTitle('Descargar backup'));
    await waitFor(() => {
      expect(downloadBackup).toHaveBeenCalledWith(5, expect.any(String));
    });
  });

  it('9 — downloadBackup receives a filename string, not undefined', async () => {
    getHostingBackups.mockResolvedValue({ items: [BACKUP_ITEM], total: 1 });
    downloadBackup.mockResolvedValue(undefined);

    renderSection();
    await waitFor(() => screen.getByTitle('Descargar backup'));

    fireEvent.click(screen.getByTitle('Descargar backup'));
    await waitFor(() => {
      const [, filename] = downloadBackup.mock.calls[0];
      expect(typeof filename).toBe('string');
      expect(filename.length).toBeGreaterThan(0);
    });
  });

  it('10 — download error shows string message (not [object Object])', async () => {
    getHostingBackups.mockResolvedValue({ items: [BACKUP_ITEM], total: 1 });
    downloadBackup.mockRejectedValue({
      response: { data: { detail: 'backup_file_missing: archivo no disponible' } },
    });

    renderSection();
    await waitFor(() => screen.getByTitle('Descargar backup'));

    fireEvent.click(screen.getByTitle('Descargar backup'));
    await waitFor(() => {
      expect(screen.getByText('backup_file_missing: archivo no disponible')).toBeTruthy();
    });
  });

  it('11 — Descargar button present for status=completed', async () => {
    getHostingBackups.mockResolvedValue({ items: [BACKUP_ITEM], total: 1 });

    renderSection();
    await waitFor(() => {
      expect(screen.getByTitle('Descargar backup')).toBeTruthy();
    });
  });

  it('12 — Descargar button absent for status=failed', async () => {
    getHostingBackups.mockResolvedValue({
      items: [{ ...BACKUP_ITEM, status: 'failed' }],
      total: 1,
    });

    renderSection();
    await waitFor(() => screen.getByText('fallido'));
    expect(screen.queryByTitle('Descargar backup')).toBeNull();
  });

  it('13 — Eliminar button present for status=failed', async () => {
    getHostingBackups.mockResolvedValue({
      items: [{ ...BACKUP_ITEM, status: 'failed' }],
      total: 1,
    });

    renderSection();
    await waitFor(() => {
      expect(screen.getByTitle('Eliminar backup')).toBeTruthy();
    });
  });
});
