/**
 * SentinelPanel UX stability tests.
 *
 * Covers:
 * 1. Source-tab change does NOT trigger a new fetch (client-side filter).
 * 2. Source-tab filters items client-side without refetch.
 * 3. Items remain visible (opacity) during status-tab refetch.
 * 4. IncidentRow uses incident_id as key — data-incident-id attribute.
 * 5. DiagnosisPanel card always visible (header always present after expand).
 * 6. Regenerating keeps previous diagnosis visible (not nulled).
 * 7. Fetch error keeps previous items on screen.
 * 8. First-load shows skeleton, not real rows.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../../services/api', () => ({
  getSentinelIncidents: vi.fn(),
  resolveIncident:      vi.fn(),
  getDiagnosis:         vi.fn(),
  triggerDiagnose:      vi.fn(),
  getIncidentActions:   vi.fn(),
  generateActions:      vi.fn(),
  approveAction:        vi.fn(),
  rejectAction:         vi.fn(),
}));

import {
  getSentinelIncidents, triggerDiagnose, getDiagnosis,
  getIncidentActions, generateActions, approveAction, rejectAction,
} from '../../services/api';
import SentinelPanel from './SentinelPanel';

// ── test data ────────────────────────────────────────────────────────────────

const makeInc = (overrides = {}) => ({
  incident_id:              42,
  source_type:              'deploy',
  incident_type:            'github_branch_not_found',
  severity:                 'warning',
  title:                    'Deploy failed: myrepo',
  status:                   'open',
  count:                    3,
  first_seen:               '2026-05-01T10:00:00Z',
  last_seen:                '2026-05-11T12:00:00Z',
  updated_at:               '2026-05-11T12:00:00Z',
  evidence:                 {},
  diagnosis_id:             null,
  diagnosis_summary:        null,
  diagnosis_root_cause:     null,
  diagnosis_steps:          null,
  diagnosis_customer_message: null,
  diagnosis_confidence:     null,
  diagnosis_source:         null,
  diagnosis_updated_at:     null,
  ...overrides,
});

const DEPLOY_INC = makeInc({ incident_id: 42, source_type: 'deploy', title: 'Deploy failed: myrepo' });
const SITE_INC   = makeInc({ incident_id: 99, source_type: 'site',   title: 'Site is down' });

const MOCK_ACTION = {
  action_id:        1,
  incident_id:      42,
  diagnosis_id:     99,
  action_type:      'customer_fix',
  title:            'Verificar acceso al repositorio GitHub',
  description:      'HostingGuard no pudo acceder al repositorio. Puede que la URL no exista, que el repositorio sea privado o que falten permisos de lectura.',
  risk_level:       'low',
  status:           'pending_approval',
  requires_approval: true,
  expected_impact:  'Corregir el acceso permitirá volver a intentar el deploy.',
  safety_notes:     'Esta recomendación no modifica el repositorio ni ejecuta comandos.',
  owner:            'cliente',
  owner_label:      'Cliente',
  can_approve:      true,
  can_reject:       true,
  can_execute:      false,
  execution_allowed: false,
  created_at:       '2026-05-11T12:00:00Z',
};

const MOCK_ACTION_APPROVED = {
  ...MOCK_ACTION,
  action_id:   2,
  status:      'approved',
  can_approve: false,
  can_reject:  true,
  approved_at: '2026-05-12T10:00:00Z',
};

const MOCK_ACTION_REJECTED = {
  ...MOCK_ACTION,
  status:      'rejected',
  can_approve: false,
  can_reject:  false,
};

const MOCK_ACTION_BLOCKED = {
  ...MOCK_ACTION,
  action_type: 'delete_container',
  title:       'Eliminar contenedor',
  status:      'blocked_by_policy',
  can_approve: false,
  can_reject:  false,
};

beforeEach(() => {
  getSentinelIncidents.mockResolvedValue({ items: [DEPLOY_INC, SITE_INC] });
  triggerDiagnose.mockResolvedValue({ ok: true });
  getDiagnosis.mockResolvedValue({
    summary:                'Fresh summary',
    root_cause:             'Fresh root cause',
    recommended_next_steps: ['Step 1'],
    customer_message:       'Customer msg',
    confidence:             0.85,
    fingerprint:            'rule_based',
    updated_at:             '2026-05-11T13:00:00Z',
  });
  getIncidentActions.mockResolvedValue({ items: [] });
  generateActions.mockResolvedValue({ ok: true });
  approveAction.mockResolvedValue({ ok: true, action_id: 1, status: 'approved' });
  rejectAction.mockResolvedValue({ ok: true, action_id: 1, status: 'rejected' });
});

afterEach(() => {
  vi.clearAllMocks();
});

// ── helper: wait for initial load ────────────────────────────────────────────

async function renderAndLoad() {
  render(<SentinelPanel />);
  // Default sourceTab is 'deploy', so deploy incident should appear after load
  await waitFor(() => expect(screen.getByText('Deploy failed: myrepo')).toBeInTheDocument());
}

// ── 1 & 2. Source-tab filtering (client-side, no refetch) ────────────────────

describe('source tab filtering', () => {
  it('does not call getSentinelIncidents again when switching source tab', async () => {
    await renderAndLoad();
    const callsBefore = getSentinelIncidents.mock.calls.length;

    // Switch to "Sitio" tab using the source-tabs container
    const sourceTabs = screen.getByText('Sitio').closest('button');
    fireEvent.click(sourceTabs);

    // Must not have made a new API call
    expect(getSentinelIncidents.mock.calls.length).toBe(callsBefore);
  });

  it('shows only deploy items on Deploy tab', async () => {
    await renderAndLoad();

    // On "Deploy" tab (default), deploy incident is visible, site is not
    expect(screen.getByText('Deploy failed: myrepo')).toBeInTheDocument();
    expect(screen.queryByText('Site is down')).not.toBeInTheDocument();
  });

  it('shows only site items when switching to Sitio tab', async () => {
    await renderAndLoad();

    fireEvent.click(screen.getByText('Sitio'));

    expect(screen.getByText('Site is down')).toBeInTheDocument();
    expect(screen.queryByText('Deploy failed: myrepo')).not.toBeInTheDocument();
  });

  it('shows all items on Todos source tab', async () => {
    await renderAndLoad();

    // The source-tab "Todos" is the first button in the tab bar
    fireEvent.click(screen.getAllByRole('button', { name: 'Todos' })[0]);

    expect(screen.getByText('Deploy failed: myrepo')).toBeInTheDocument();
    expect(screen.getByText('Site is down')).toBeInTheDocument();
  });
});

// ── 3. Items stay visible during status-tab refetch ──────────────────────────

describe('status tab refetch keeps data visible', () => {
  it('previous items remain in DOM while loading new status', async () => {
    await renderAndLoad();

    // Make next fetch slow (never resolves immediately)
    let resolveNewFetch;
    getSentinelIncidents.mockImplementation(
      () => new Promise(r => { resolveNewFetch = r; }),
    );

    // Switch to "Resueltos" — triggers refetch
    fireEvent.click(screen.getByText('Resueltos'));

    // Previous deploy item must still be in the DOM (kept while loading)
    expect(screen.getByText('Deploy failed: myrepo')).toBeInTheDocument();

    // Clean up pending promise
    await act(async () => { resolveNewFetch({ items: [] }); });
  });
});

// ── 4. IncidentRow key is incident_id ────────────────────────────────────────

describe('IncidentRow key stability', () => {
  it('uses data-incident-id attribute for stable identification', async () => {
    await renderAndLoad();

    const row = screen.getByText('Deploy failed: myrepo')
      .closest('[data-incident-id]');
    expect(row).toBeTruthy();
    expect(row.getAttribute('data-incident-id')).toBe('42');
  });
});

// ── 5. DiagnosisPanel card always mounted after expand ───────────────────────

describe('DiagnosisPanel always-mounted', () => {
  it('shows Diagnóstico IA header immediately after expanding incident', async () => {
    await renderAndLoad();

    fireEvent.click(screen.getByText('Deploy failed: myrepo'));

    // The DiagnosisPanel header is always in the DOM once expanded
    expect(screen.getByText('Diagnóstico IA')).toBeInTheDocument();
  });

  it('shows empty state message before any diagnosis is generated', async () => {
    await renderAndLoad();

    fireEvent.click(screen.getByText('Deploy failed: myrepo'));

    expect(screen.getByText(/sin diagnóstico/i)).toBeInTheDocument();
  });

  it('shows Generar diagnóstico button when no diagnosis exists', async () => {
    await renderAndLoad();

    fireEvent.click(screen.getByText('Deploy failed: myrepo'));

    expect(screen.getByTestId('diagnose-btn')).toBeInTheDocument();
    expect(screen.getByTestId('diagnose-btn')).toHaveTextContent('Generar diagnóstico');
  });
});

// ── 6. Regenerating keeps previous diagnosis visible ─────────────────────────

describe('DiagnosisPanel regenerate', () => {
  it('previous diagnosis stays visible while regenerating', async () => {
    const incWithDiag = makeInc({
      diagnosis_summary:        'Existing summary',
      diagnosis_root_cause:     'Existing root cause',
      diagnosis_steps:          ['Existing step'],
      diagnosis_customer_message: 'Existing message',
      diagnosis_confidence:     0.9,
      diagnosis_source:         'rule_based',
      diagnosis_updated_at:     '2026-05-10T10:00:00Z',
    });
    getSentinelIncidents.mockResolvedValue({ items: [incWithDiag] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByText('Existing summary'));

    // Make trigger pause so we can observe mid-regeneration state
    let resolveTriggered;
    triggerDiagnose.mockImplementation(() => new Promise(r => { resolveTriggered = r; }));

    fireEvent.click(screen.getByTestId('diagnose-btn'));

    // Previous summary must NOT be removed while regenerating
    expect(screen.getByText('Existing summary')).toBeInTheDocument();
    expect(screen.getByText('Existing root cause')).toBeInTheDocument();

    // Cleanup
    await act(async () => {
      resolveTriggered({ ok: true });
      // getDiagnosis will resolve from mock
    });
  });

  it('shows Regenerar label when diagnosis already exists', async () => {
    const incWithDiag = makeInc({
      diagnosis_summary:    'Old summary',
      diagnosis_updated_at: '2026-05-10T10:00:00Z',
    });
    getSentinelIncidents.mockResolvedValue({ items: [incWithDiag] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByText('Old summary'));

    expect(screen.getByTestId('diagnose-btn')).toHaveTextContent('Regenerar');
  });
});

// ── 7. Fetch error keeps previous items visible ───────────────────────────────

describe('error handling', () => {
  it('shows error inline and keeps previous items in DOM', async () => {
    await renderAndLoad();

    // Next fetch fails
    getSentinelIncidents.mockRejectedValue({
      response: { data: { detail: 'Network error' } },
    });

    // Switch status tab to trigger refetch
    fireEvent.click(screen.getByText('Resueltos'));

    await waitFor(() => expect(screen.getByText(/Network error/i)).toBeInTheDocument());

    // Previous items still present
    expect(screen.getByText('Deploy failed: myrepo')).toBeInTheDocument();
    // Error message includes "últimos datos"
    expect(screen.getByText(/últimos datos disponibles/i)).toBeInTheDocument();
  });
});

// ── 8. First-load skeleton ────────────────────────────────────────────────────

describe('loading states', () => {
  it('does not show incident titles while first load is pending', async () => {
    let resolveLoad;
    getSentinelIncidents.mockImplementation(
      () => new Promise(r => { resolveLoad = r; }),
    );

    render(<SentinelPanel />);

    // Skeleton is shown, real content is not yet present
    expect(screen.queryByText('Deploy failed: myrepo')).not.toBeInTheDocument();

    await act(async () => { resolveLoad({ items: [DEPLOY_INC] }); });
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
  });

  it('shows Actualizando indicator during subsequent refresh', async () => {
    await renderAndLoad();

    let resolveRefresh;
    getSentinelIncidents.mockImplementation(
      () => new Promise(r => { resolveRefresh = r; }),
    );

    // Trigger manual refresh via the RefreshCw button
    const refreshBtn = screen.getAllByRole('button').find(b => !b.textContent.trim());
    fireEvent.click(refreshBtn);

    expect(screen.getByText(/Actualizando/i)).toBeInTheDocument();

    await act(async () => { resolveRefresh({ items: [DEPLOY_INC] }); });
  });
});

// ── ActionsPanel ─────────────────────────────────────────────────────────────

async function expandIncident(title = 'Deploy failed: myrepo') {
  render(<SentinelPanel />);
  await waitFor(() => screen.getByText(title));
  fireEvent.click(screen.getByText(title));
}

describe('ActionsPanel', () => {
  it('renders "Acciones recomendadas" header after expand', async () => {
    await expandIncident();
    await waitFor(() =>
      expect(screen.getByText('Acciones recomendadas')).toBeInTheDocument(),
    );
  });

  it('calls getIncidentActions on expand', async () => {
    await expandIncident();
    await waitFor(() => expect(getIncidentActions).toHaveBeenCalledWith(42));
  });

  it('shows persistent phase notice about no execution', async () => {
    await expandIncident();
    await waitFor(() =>
      expect(screen.getByTestId('phase-notice')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('phase-notice').textContent).toMatch(/no ejecuta comandos/i);
  });

  it('shows empty state message when no actions', async () => {
    getIncidentActions.mockResolvedValue({ items: [] });
    await expandIncident();
    await waitFor(() =>
      expect(screen.getByText(/Genera un diagnóstico/i)).toBeInTheDocument(),
    );
  });

  it('shows action card with title when actions are loaded', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION] });
    await expandIncident();
    await waitFor(() =>
      expect(screen.getByText('Verificar acceso al repositorio GitHub')).toBeInTheDocument(),
    );
  });

  it('shows risk badge in Spanish (Bajo for low)', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION] });
    await expandIncident();
    await waitFor(() => expect(screen.getByTestId('risk-badge')).toHaveTextContent('Bajo'));
  });

  it('shows owner label on action card', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION] });
    await expandIncident();
    await waitFor(() => expect(screen.getByTestId('owner-label')).toHaveTextContent('Cliente'));
  });

  it('shows status label in Spanish for pending_approval', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION] });
    await expandIncident();
    await waitFor(() =>
      expect(screen.getByTestId('status-label')).toHaveTextContent('Pendiente de revisión'),
    );
  });

  it('shows Approve and Reject buttons only for pending_approval', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION] });
    await expandIncident();
    await waitFor(() => screen.getByTestId('approve-btn'));
    expect(screen.getByTestId('approve-btn')).toBeInTheDocument();
    expect(screen.getByTestId('reject-btn')).toBeInTheDocument();
  });

  it('clicking Approve shows inline confirmation, not immediate call', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION] });
    await expandIncident();
    await waitFor(() => screen.getByTestId('approve-btn'));

    fireEvent.click(screen.getByTestId('approve-btn'));

    // Should show confirm button, not call approveAction yet
    await waitFor(() => screen.getByTestId('confirm-approve-btn'));
    expect(approveAction).not.toHaveBeenCalled();
  });

  it('confirm approve calls approveAction', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION] });
    await expandIncident();
    await waitFor(() => screen.getByTestId('approve-btn'));

    fireEvent.click(screen.getByTestId('approve-btn'));
    await waitFor(() => screen.getByTestId('confirm-approve-btn'));
    fireEvent.click(screen.getByTestId('confirm-approve-btn'));

    await waitFor(() => expect(approveAction).toHaveBeenCalledWith(1));
  });

  it('calls rejectAction when reject is clicked', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION] });
    await expandIncident();
    await waitFor(() => screen.getByTestId('reject-btn'));

    fireEvent.click(screen.getByTestId('reject-btn'));

    await waitFor(() => expect(rejectAction).toHaveBeenCalledWith(1));
  });

  it('approved action shows "Aprobada, no ejecutada" status label', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    await expandIncident();
    await waitFor(() =>
      expect(screen.getByTestId('status-label')).toHaveTextContent('Aprobada, no ejecutada'),
    );
  });

  it('approved action shows notice about no automatic execution', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    await expandIncident();
    await waitFor(() => screen.getByTestId('approved-notice'));
    expect(screen.getByTestId('approved-notice').textContent).toMatch(/no existe ejecución automática/i);
  });

  it('approved action hides Approve button', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    await expandIncident();
    await waitFor(() => expect(screen.queryByTestId('approve-btn')).not.toBeInTheDocument());
  });

  it('rejected action hides Approve and Reject buttons', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_REJECTED] });
    await expandIncident();
    await waitFor(() => expect(screen.queryByTestId('approve-btn')).not.toBeInTheDocument());
    expect(screen.queryByTestId('reject-btn')).not.toBeInTheDocument();
  });

  it('rejected action shows "Rechazada" status label', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_REJECTED] });
    await expandIncident();
    await waitFor(() =>
      expect(screen.getByTestId('status-label')).toHaveTextContent('Rechazada'),
    );
  });

  it('blocked_by_policy action shows "Bloqueada por política"', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_BLOCKED] });
    await expandIncident();
    await waitFor(() => screen.getByTestId('blocked-notice'));
    expect(screen.getByTestId('blocked-notice').textContent).toMatch(/no puede ejecutarse/i);
  });

  it('no Ejecutar button exists anywhere', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION, MOCK_ACTION_APPROVED] });
    await expandIncident();
    await waitFor(() => screen.getAllByTestId('action-card'));
    const buttons = screen.getAllByRole('button');
    const execBtn = buttons.find(b => /ejecutar/i.test(b.textContent));
    expect(execBtn).toBeUndefined();
  });

  it('calls generateActions when generate button is clicked with diagnosis', async () => {
    const incWithDiag = makeInc({ diagnosis_summary: 'Has diag', diagnosis_updated_at: '2026-05-11T10:00:00Z' });
    getSentinelIncidents.mockResolvedValue({ items: [incWithDiag] });
    getIncidentActions.mockResolvedValue({ items: [] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));

    await waitFor(() =>
      expect(screen.getByText(/Sin recomendaciones todavía/i)).toBeInTheDocument(),
    );

    const genBtn = screen.getByTestId('generate-actions-btn');
    expect(genBtn).not.toBeDisabled();
    fireEvent.click(genBtn);

    await waitFor(() => expect(generateActions).toHaveBeenCalledWith(42, false));
  });

  it('github_private_repo description does not mention only token', async () => {
    const githubAction = {
      ...MOCK_ACTION,
      action_type:   'customer_fix',
      title:         'Verificar acceso al repositorio GitHub',
      description:   'HostingGuard no pudo acceder al repositorio. Puede que la URL no exista, que el repositorio sea privado o que falten permisos.',
      owner_label:   'Cliente',
      can_approve:   true,
      can_reject:    true,
    };
    getIncidentActions.mockResolvedValue({ items: [githubAction] });
    await expandIncident();
    await waitFor(() => screen.getByText('Verificar acceso al repositorio GitHub'));
    const desc = screen.getByText(/no pudo acceder al repositorio/i);
    expect(desc).toBeInTheDocument();
    // Description must not say ONLY token
    expect(desc.textContent).not.toMatch(/^Revisar permisos del token/);
  });
});
