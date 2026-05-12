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
  generateActionPlan:   vi.fn(),
  getActionPlans:       vi.fn(),
  cancelPlan:           vi.fn(),
}));

import {
  getSentinelIncidents, triggerDiagnose, getDiagnosis,
  getIncidentActions, generateActions, approveAction, rejectAction,
  generateActionPlan, getActionPlans, cancelPlan,
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
  can_reject:  false,
  approved_at: '2026-05-12T10:00:00Z',
  rules_version: null,  // simulates old v1 row without version
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

const MOCK_PLAN = {
  plan_id:                100,
  action_id:              2,
  incident_id:            42,
  diagnosis_id:           99,
  plan_type:              'customer_fix',
  status:                 'draft',
  risk_level:             'low',
  execution_allowed:      false,
  requires_final_approval: true,
  title:                  'Plan de corrección para el cliente',
  summary:                'El cliente debe realizar cambios.',
  prechecks:              [{ order: 1, description: 'Verificar acceso al repositorio' }],
  steps:                  [{ order: 1, description: 'Notificar al cliente' }],
  rollback_steps:         [],
  expected_impact:        'El incidente se resolverá.',
  safety_notes:           'HostingGuard no modifica nada.',
  blocked_reason:         '',
  planner_version:        'planner_v1',
  context_hash:           'hash123',
  created_by:             'admin',
  created_at:             '2026-05-12T10:00:00Z',
  updated_at:             '2026-05-12T10:00:00Z',
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
  generateActionPlan.mockResolvedValue({ ok: true, created: true, plan: MOCK_PLAN });
  getActionPlans.mockResolvedValue({ items: [] });
  cancelPlan.mockResolvedValue({ ok: true, plan_id: 100, status: 'cancelled' });
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

  it('open incident without actions shows Generar button when diagnosis exists', async () => {
    const incWithDiag = makeInc({
      diagnosis_summary:    'Has diag',
      diagnosis_updated_at: '2026-05-11T10:00:00Z',
    });
    getSentinelIncidents.mockResolvedValue({ items: [incWithDiag] });
    getIncidentActions.mockResolvedValue({ items: [] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));

    await waitFor(() =>
      expect(screen.getByTestId('generate-actions-btn')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('generate-actions-btn')).not.toBeDisabled();
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

// ── ActionsPanel — resolved incident ─────────────────────────────────────────

describe('ActionsPanel — resolved incident', () => {
  async function expandResolved() {
    const resolvedInc = makeInc({ status: 'resolved', incident_id: 42, source_type: 'deploy' });
    getSentinelIncidents.mockResolvedValue({ items: [resolvedInc] });
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
  }

  it('does not show Generar recomendaciones button for resolved incident', async () => {
    getIncidentActions.mockResolvedValue({ items: [] });
    await expandResolved();
    await waitFor(() => expect(getIncidentActions).toHaveBeenCalled());
    expect(screen.queryByTestId('generate-actions-btn')).not.toBeInTheDocument();
  });

  it('shows resolved-notice for resolved incident', async () => {
    getIncidentActions.mockResolvedValue({ items: [] });
    await expandResolved();
    await waitFor(() =>
      expect(screen.getByTestId('resolved-notice')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('resolved-notice').textContent).toMatch(/ya está resuelto/i);
  });

  it('does not show phase-notice for resolved incident', async () => {
    getIncidentActions.mockResolvedValue({ items: [] });
    await expandResolved();
    await waitFor(() => expect(getIncidentActions).toHaveBeenCalled());
    expect(screen.queryByTestId('phase-notice')).not.toBeInTheDocument();
  });
});

// ── ActionsPanel — approved hides Rechazar ────────────────────────────────────

describe('ActionsPanel — approved action buttons', () => {
  it('approved action hides Rechazar button', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    await expandIncident();
    await waitFor(() => expect(screen.queryByTestId('approve-btn')).not.toBeInTheDocument());
    expect(screen.queryByTestId('reject-btn')).not.toBeInTheDocument();
  });

  it('approved action hides Aprobar button', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    await expandIncident();
    await waitFor(() => expect(screen.queryByTestId('approve-btn')).not.toBeInTheDocument());
  });

  it('approved action shows Aprobada status label', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    await expandIncident();
    await waitFor(() =>
      expect(screen.getByTestId('status-label')).toHaveTextContent('Aprobada, no ejecutada'),
    );
  });
});

// ── ActionsPanel — Regenerar vs Generar ──────────────────────────────────────

describe('ActionsPanel — Regenerar / Generar button', () => {
  it('shows Generar when no actions exist', async () => {
    getIncidentActions.mockResolvedValue({ items: [] });
    await expandIncident();
    // hasDiagnosis=false → button disabled but label is "Generar recomendaciones"
    await waitFor(() =>
      expect(screen.getByTestId('generate-actions-btn')).toHaveTextContent('Generar recomendaciones'),
    );
  });

  it('shows Regenerar when actions exist (old rules_version null)', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    await expandIncident();
    await waitFor(() =>
      expect(screen.getByTestId('generate-actions-btn')).toHaveTextContent('Regenerar recomendaciones'),
    );
  });

  it('Generar button calls generateActions with force=false', async () => {
    const incWithDiag = makeInc({ diagnosis_summary: 'Has diag', diagnosis_updated_at: '2026-05-11T10:00:00Z' });
    getSentinelIncidents.mockResolvedValue({ items: [incWithDiag] });
    getIncidentActions.mockResolvedValue({ items: [] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByText(/Sin recomendaciones todavía/i));

    fireEvent.click(screen.getByTestId('generate-actions-btn'));
    await waitFor(() => expect(generateActions).toHaveBeenCalledWith(42, false));
  });

  it('Regenerar button calls generateActions with force=true', async () => {
    const incWithDiag = makeInc({ diagnosis_summary: 'Has diag', diagnosis_updated_at: '2026-05-11T10:00:00Z' });
    getSentinelIncidents.mockResolvedValue({ items: [incWithDiag] });
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() =>
      expect(screen.getByTestId('generate-actions-btn')).toHaveTextContent('Regenerar recomendaciones'),
    );

    fireEvent.click(screen.getByTestId('generate-actions-btn'));
    await waitFor(() => expect(generateActions).toHaveBeenCalledWith(42, true));
  });
});

// ── Phase 3B: Execution Plan UI ───────────────────────────────────────────────

async function expandIncidentWithApproved() {
  getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
  getActionPlans.mockResolvedValue({ items: [] });
  render(<SentinelPanel />);
  await waitFor(() => screen.getByText('Deploy failed: myrepo'));
  fireEvent.click(screen.getByText('Deploy failed: myrepo'));
  await waitFor(() => screen.getByTestId('approved-notice'));
}

describe('Phase 3B — plan button visibility', () => {
  it('pending action does not show generate-plan-btn', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION] });
    await expandIncident();
    await waitFor(() => screen.getByTestId('action-card'));
    expect(screen.queryByTestId('generate-plan-btn')).not.toBeInTheDocument();
  });

  it('rejected action does not show generate-plan-btn', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_REJECTED] });
    await expandIncident();
    await waitFor(() => screen.getByTestId('action-card'));
    expect(screen.queryByTestId('generate-plan-btn')).not.toBeInTheDocument();
  });

  it('approved action with no plan shows generate-plan-btn', async () => {
    getActionPlans.mockResolvedValue({ items: [] });
    await expandIncidentWithApproved();
    await waitFor(() =>
      expect(screen.getByTestId('generate-plan-btn')).toBeInTheDocument(),
    );
  });

  it('approved action with existing plan shows Regenerar plan button', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [MOCK_PLAN] });
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    expect(screen.getByTestId('generate-plan-btn')).toHaveTextContent('Regenerar plan');
  });
});

describe('Phase 3B — plan generation', () => {
  it('clicking generate-plan-btn calls generateActionPlan with actionId and force=false', async () => {
    getActionPlans.mockResolvedValue({ items: [] });
    await expandIncidentWithApproved();
    await waitFor(() => screen.getByTestId('generate-plan-btn'));
    fireEvent.click(screen.getByTestId('generate-plan-btn'));
    await waitFor(() => expect(generateActionPlan).toHaveBeenCalledWith(2, false));
  });

  it('after generation, PlanCard appears (plan fetched from DB via getActionPlans)', async () => {
    generateActionPlan.mockResolvedValue({ ok: true, created: true, plan: MOCK_PLAN });
    await expandIncidentWithApproved(); // initial load uses default { items: [] }
    // Next getActionPlans call (from handleGeneratePlan) returns the persisted plan
    getActionPlans.mockResolvedValueOnce({ items: [MOCK_PLAN] });
    await waitFor(() => screen.getByTestId('generate-plan-btn'));
    fireEvent.click(screen.getByTestId('generate-plan-btn'));
    await waitFor(() => screen.getByTestId('plan-card'));
    expect(screen.getByTestId('plan-card')).toBeInTheDocument();
  });
});

describe('Phase 3B — PlanCard fields', () => {
  beforeEach(() => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [MOCK_PLAN] });
  });

  it('plan-card renders plan title', async () => {
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    expect(screen.getByTestId('plan-card').textContent).toContain('Plan de corrección para el cliente');
  });

  it('plan-card shows status label', async () => {
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-status-label'));
    expect(screen.getByTestId('plan-status-label').textContent).toBe('Borrador');
  });

  it('plan-card shows no-execute notice', async () => {
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-no-execute-notice'));
    expect(screen.getByTestId('plan-no-execute-notice').textContent).toMatch(/no ejecuta comandos/i);
  });

  it('plan-card does not render an Ejecutar button', async () => {
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    const allButtons = screen.getAllByRole('button');
    const execBtn = allButtons.find(b => /ejecutar/i.test(b.textContent));
    expect(execBtn).toBeUndefined();
  });
});

describe('Phase 3B — plan cancel', () => {
  it('plan with non-cancelled status shows cancel-plan-btn', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [MOCK_PLAN] });
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    // Expand the plan card to see cancel button
    fireEvent.click(screen.getByTestId('plan-card').querySelector('div'));
    await waitFor(() => screen.getByTestId('cancel-plan-btn'));
    expect(screen.getByTestId('cancel-plan-btn')).toBeInTheDocument();
  });

  it('clicking cancel-plan-btn calls cancelPlan', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [MOCK_PLAN] });
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    // Expand plan card
    fireEvent.click(screen.getByTestId('plan-card').querySelector('div'));
    await waitFor(() => screen.getByTestId('cancel-plan-btn'));
    fireEvent.click(screen.getByTestId('cancel-plan-btn'));
    await waitFor(() => expect(cancelPlan).toHaveBeenCalledWith(100));
  });

  it('blocked plan shows blocked reason', async () => {
    const blockedPlan = { ...MOCK_PLAN, status: 'blocked_by_policy', blocked_reason: 'Bloqueado por política de seguridad' };
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [blockedPlan] });
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    // Expand plan card
    fireEvent.click(screen.getByTestId('plan-card').querySelector('div'));
    await waitFor(() => screen.getByTestId('plan-blocked-reason'));
    expect(screen.getByTestId('plan-blocked-reason').textContent).toMatch(/bloqueado/i);
  });

  it('superseded plan treated as inactive — no PlanCard and no cancel-plan-btn', async () => {
    const supersededPlan = { ...MOCK_PLAN, status: 'superseded' };
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [supersededPlan] });
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('approved-notice'));
    // Superseded plan is excluded from active plan check → no PlanCard, no cancel button
    expect(screen.queryByTestId('plan-card')).not.toBeInTheDocument();
    expect(screen.queryByTestId('cancel-plan-btn')).not.toBeInTheDocument();
    // Generate plan button still visible (no active plan)
    expect(screen.getByTestId('generate-plan-btn')).toHaveTextContent('Generar plan');
  });
});

// ── Phase 3B — plan refresh from DB ──────────────────────────────────────────

describe('Phase 3B — plan refresh from DB', () => {
  it('handleGeneratePlan calls getActionPlans after generateActionPlan', async () => {
    generateActionPlan.mockResolvedValue({ ok: true, created: true, plan: MOCK_PLAN });

    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('generate-plan-btn'));

    // Set up: next getActionPlans call (refresh after generate) returns the plan
    const callsBefore = getActionPlans.mock.calls.length;
    getActionPlans.mockResolvedValueOnce({ items: [MOCK_PLAN] });
    fireEvent.click(screen.getByTestId('generate-plan-btn'));

    await waitFor(() => expect(getActionPlans.mock.calls.length).toBeGreaterThan(callsBefore));
    await waitFor(() => screen.getByTestId('plan-card'));
  });

  it('generate-plan-btn calls generateActionPlan with force=true when plan exists', async () => {
    getActionPlans.mockResolvedValue({ items: [MOCK_PLAN] });
    generateActionPlan.mockResolvedValue({ ok: true, created: true, plan: MOCK_PLAN });
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));

    fireEvent.click(screen.getByTestId('generate-plan-btn'));
    await waitFor(() => expect(generateActionPlan).toHaveBeenCalledWith(2, true));
  });

  it('handleCancelPlan calls getActionPlans after cancelPlan', async () => {
    getActionPlans
      .mockResolvedValueOnce({ items: [MOCK_PLAN] })
      .mockResolvedValueOnce({ items: [] });
    cancelPlan.mockResolvedValue({ ok: true, plan_id: 100, status: 'cancelled' });
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    fireEvent.click(screen.getByTestId('plan-card').querySelector('div'));
    await waitFor(() => screen.getByTestId('cancel-plan-btn'));

    const callsBefore = getActionPlans.mock.calls.length;
    fireEvent.click(screen.getByTestId('cancel-plan-btn'));

    await waitFor(() => expect(getActionPlans.mock.calls.length).toBeGreaterThan(callsBefore));
  });
});

// ── Phase 3B — current vs historical actions ─────────────────────────────────

const MOCK_ACTION_APPROVED_V2 = {
  ...MOCK_ACTION_APPROVED,
  action_id:     3,
  rules_version: 'actions_v2',
  created_at:    '2026-05-12T11:00:00Z', // newer than MOCK_ACTION_APPROVED
};

describe('Phase 3B — current vs historical grouping', () => {
  it('two approved actions of same action_type show historical-toggle', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED, MOCK_ACTION_APPROVED_V2] });
    getActionPlans.mockResolvedValue({ items: [] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));

    await waitFor(() => expect(screen.getByTestId('historical-toggle')).toBeInTheDocument());
    expect(screen.getByTestId('historical-toggle').textContent).toMatch(/versiones anteriores/i);
  });

  it('newer action_type shown as current, older collapsed in historical', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED, MOCK_ACTION_APPROVED_V2] });
    getActionPlans.mockResolvedValue({ items: [] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));

    // Only one action-card visible (the current one), historical is collapsed
    await waitFor(() => expect(screen.getAllByTestId('action-card')).toHaveLength(1));
    expect(screen.getByTestId('historical-toggle')).toBeInTheDocument();
  });

  it('plan from action_id=2 not shown under action_id=3 card', async () => {
    const planForOld = { ...MOCK_PLAN, action_id: 2, plan_id: 200 };
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED, MOCK_ACTION_APPROVED_V2] });
    getActionPlans.mockImplementation(id =>
      Promise.resolve({ items: id === 2 ? [planForOld] : [] }),
    );

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));

    // Current action (action_id=3, V2) shown — it has no plan
    await waitFor(() => screen.getByTestId('action-card'));
    // generate-plan-btn should say "Generar plan" (no plan for action_id=3)
    await waitFor(() =>
      expect(screen.getByTestId('generate-plan-btn')).toHaveTextContent('Generar plan'),
    );
    // plan-card for action_id=2 must NOT appear in the main card
    expect(screen.queryByTestId('plan-card')).not.toBeInTheDocument();
  });

  it('single action of each type shows no historical-toggle', async () => {
    const actionTypeB = { ...MOCK_ACTION_APPROVED, action_id: 5, action_type: 'admin_review' };
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED, actionTypeB] });
    getActionPlans.mockResolvedValue({ items: [] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));

    // Both are current (different action_types), no historical
    await waitFor(() => expect(screen.getAllByTestId('action-card')).toHaveLength(2));
    expect(screen.queryByTestId('historical-toggle')).not.toBeInTheDocument();
  });
});

// ── Phase 3B.1 — PlanCard copy plan ──────────────────────────────────────────

function mockClipboard() {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    writable: true,
    configurable: true,
  });
  return writeText;
}

async function openExpandedPlanCard() {
  getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
  getActionPlans.mockResolvedValue({ items: [MOCK_PLAN] });
  render(<SentinelPanel />);
  await waitFor(() => screen.getByText('Deploy failed: myrepo'));
  fireEvent.click(screen.getByText('Deploy failed: myrepo'));
  await waitFor(() => screen.getByTestId('plan-card'));
  // Expand plan card body
  fireEvent.click(screen.getByTestId('plan-card').querySelector('div'));
  await waitFor(() => screen.getByTestId('copy-plan-btn'));
}

describe('Phase 3B.1 — PlanCard copy plan', () => {
  it('shows Copiar plan button', async () => {
    await openExpandedPlanCard();
    expect(screen.getByTestId('copy-plan-btn')).toBeInTheDocument();
  });

  it('clicking Copiar plan calls clipboard.writeText', async () => {
    const writeText = mockClipboard();
    await openExpandedPlanCard();
    fireEvent.click(screen.getByTestId('copy-plan-btn'));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  });

  it('Copiar plan text includes no-execute disclaimer', async () => {
    let capturedText = '';
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn(text => { capturedText = text; return Promise.resolve(); }) },
      writable: true,
      configurable: true,
    });
    await openExpandedPlanCard();
    fireEvent.click(screen.getByTestId('copy-plan-btn'));
    await waitFor(() => expect(capturedText).toBeTruthy());
    expect(capturedText).toMatch(/no ejecuta cambios/i);
  });

  it('Copiar plan text does not contain raw JSON object syntax', async () => {
    let capturedText = '';
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn(text => { capturedText = text; return Promise.resolve(); }) },
      writable: true,
      configurable: true,
    });
    await openExpandedPlanCard();
    fireEvent.click(screen.getByTestId('copy-plan-btn'));
    await waitFor(() => expect(capturedText).toBeTruthy());
    expect(capturedText).not.toContain('"plan_id"');
    expect(capturedText).not.toContain('"steps"');
  });
});

// ── Phase 3B.1 — PlanCard can_cancel ─────────────────────────────────────────

describe('Phase 3B.1 — PlanCard can_cancel', () => {
  it('can_cancel=false from API hides cancel-plan-btn', async () => {
    const planNoCanccel = { ...MOCK_PLAN, can_cancel: false };
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [planNoCanccel] });
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    fireEvent.click(screen.getByTestId('plan-card').querySelector('div'));
    await waitFor(() => screen.getByTestId('copy-plan-btn'));
    expect(screen.queryByTestId('cancel-plan-btn')).not.toBeInTheDocument();
  });

  it('can_cancel=true from API shows cancel-plan-btn', async () => {
    const planCanCancel = { ...MOCK_PLAN, can_cancel: true };
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [planCanCancel] });
    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    fireEvent.click(screen.getByTestId('plan-card').querySelector('div'));
    await waitFor(() => screen.getByTestId('cancel-plan-btn'));
    expect(screen.getByTestId('cancel-plan-btn')).toBeInTheDocument();
  });
});

// ── Phase 3B.1 — cancel success message ──────────────────────────────────────

describe('Phase 3B.1 — cancel success message', () => {
  it('shows "Plan cancelado. No se ejecutó ninguna acción." after cancel', async () => {
    getActionPlans
      .mockResolvedValueOnce({ items: [MOCK_PLAN] })
      .mockResolvedValue({ items: [] });
    cancelPlan.mockResolvedValue({ ok: true, plan_id: 100, status: 'cancelled' });
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    fireEvent.click(screen.getByTestId('plan-card').querySelector('div'));
    await waitFor(() => screen.getByTestId('cancel-plan-btn'));
    fireEvent.click(screen.getByTestId('cancel-plan-btn'));

    await waitFor(() =>
      expect(screen.getByTestId('cancel-success-msg')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('cancel-success-msg').textContent).toMatch(
      /no se ejecutó ninguna acción/i,
    );
  });
});

// ── Phase 3B.1 — Planes anteriores (history plans) ───────────────────────────

describe('Phase 3B.1 — history plans in PlanCard', () => {
  const ACTIVE_PLAN = {
    ...MOCK_PLAN, plan_id: 101, status: 'ready_for_review',
    status_label: 'Listo para revisión', title: 'Plan activo', can_cancel: true,
  };
  const CANCELLED_PLAN = {
    ...MOCK_PLAN, plan_id: 100, status: 'cancelled',
    status_label: 'Cancelado', title: 'Plan cancelado anterior', can_cancel: false,
  };

  it('shows history-plans-toggle when cancelled plan exists alongside active plan', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [ACTIVE_PLAN, CANCELLED_PLAN] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    fireEvent.click(screen.getByTestId('plan-card').querySelector('div'));

    await waitFor(() =>
      expect(screen.getByTestId('history-plans-toggle')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('history-plans-toggle').textContent).toMatch(/planes anteriores/i);
  });

  it('cancelled plan title appears in history list after clicking toggle', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [ACTIVE_PLAN, CANCELLED_PLAN] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    fireEvent.click(screen.getByTestId('plan-card').querySelector('div'));
    await waitFor(() => screen.getByTestId('history-plans-toggle'));
    fireEvent.click(screen.getByTestId('history-plans-toggle'));

    await waitFor(() =>
      expect(screen.getByTestId('history-plans-list')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('history-plans-list').textContent).toContain('Plan cancelado anterior');
  });

  it('no history-plans-toggle when only one plan exists', async () => {
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [MOCK_PLAN] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));
    fireEvent.click(screen.getByTestId('plan-card').querySelector('div'));
    await waitFor(() => screen.getByTestId('copy-plan-btn'));

    expect(screen.queryByTestId('history-plans-toggle')).not.toBeInTheDocument();
  });
});

// ── Phase 3B.1 — Copiar informe includes plan data ───────────────────────────

describe('Phase 3B.1 — Copiar informe includes plan and security note', () => {
  async function renderWithPlan() {
    let capturedText = '';
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn(text => { capturedText = text; return Promise.resolve(); }) },
      writable: true,
      configurable: true,
    });
    getIncidentActions.mockResolvedValue({ items: [MOCK_ACTION_APPROVED] });
    getActionPlans.mockResolvedValue({ items: [MOCK_PLAN] });

    render(<SentinelPanel />);
    await waitFor(() => screen.getByText('Deploy failed: myrepo'));
    fireEvent.click(screen.getByText('Deploy failed: myrepo'));
    await waitFor(() => screen.getByTestId('plan-card'));

    const copyInfoBtn = screen.getAllByRole('button').find(
      b => b.textContent.trim() === 'Copiar informe',
    );
    fireEvent.click(copyInfoBtn);
    await waitFor(() => expect(capturedText).toBeTruthy());
    return capturedText;
  }

  it('report includes security note about no automatic execution', async () => {
    const text = await renderWithPlan();
    expect(text).toMatch(/no ejecutó cambios automáticamente/i);
  });

  it('report includes plan title when plan exists', async () => {
    const text = await renderWithPlan();
    expect(text).toContain('Plan de corrección para el cliente');
  });

  it('report includes "Ejecución permitida: No" for plan', async () => {
    const text = await renderWithPlan();
    expect(text).toMatch(/Ejecución permitida:\s*No/i);
  });
});
