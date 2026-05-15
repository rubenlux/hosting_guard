/**
 * IncidentKnowledgePanel tests (P0.2)
 *
 * Covers:
 * 1.  renders search textarea
 * 2.  search calls matchKnowledgeIncident with typed text
 * 3.  match result shows incident_id
 * 4.  match result shows safe_actions
 * 5.  match result shows forbidden_actions
 * 6.  runbooks list renders on load
 * 7.  runbook row click loads detail
 * 8.  runbook detail shows body
 * 9.  safe action validator shows allowed true
 * 10. safe action validator shows allowed false
 * 11. 401 response shows "No autenticado"
 * 12. backend error shows error message
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../../services/api', () => ({
  listKnowledgeRunbooks: vi.fn(),
  getKnowledgeRunbook: vi.fn(),
  matchKnowledgeIncident: vi.fn(),
  validateKnowledgeSafeAction: vi.fn(),
  listKnowledgeSafeActions: vi.fn(),
}));

import {
  listKnowledgeRunbooks,
  getKnowledgeRunbook,
  matchKnowledgeIncident,
  validateKnowledgeSafeAction,
  listKnowledgeSafeActions,
} from '../../services/api';
import IncidentKnowledgePanel from './IncidentKnowledgePanel';

// ── Mock data ─────────────────────────────────────────────────────────────────

const MOCK_MATCH = {
  matched_runbook: {
    incident_id: 'WELCOME_TO_NGINX_EMPTY_SITE',
    severity: 'critical',
    auto_repair_allowed: false,
    safe_actions: ['recreate_static_nginx_container_with_mount'],
    forbidden_actions: ['delete_client_files'],
    signature_matched: 'Welcome to nginx!',
  },
  safe_actions: ['recreate_static_nginx_container_with_mount'],
  forbidden_actions: ['delete_client_files'],
  confidence: 1.0,
  match_method: 'exact_signature',
};

const MOCK_RUNBOOKS = {
  runbooks: [
    { incident_id: 'WELCOME_TO_NGINX_EMPTY_SITE', severity: 'critical', auto_repair_allowed: false, safe_actions: [], forbidden_actions: [] },
    { incident_id: 'CONTAINER_WITH_EMPTY_MOUNTS', severity: 'high',     auto_repair_allowed: false, safe_actions: [], forbidden_actions: [] },
  ],
  total: 2,
};

const MOCK_RUNBOOK_DETAIL = {
  incident_id: 'WELCOME_TO_NGINX_EMPTY_SITE',
  body: '# WELCOME_TO_NGINX_EMPTY_SITE\n\nSíntoma: sitio muestra Welcome to nginx',
  safe_actions: ['recreate_static_nginx_container_with_mount'],
  forbidden_actions: ['delete_client_files'],
};

const MOCK_SAFE_ACTIONS = {
  safe_actions: [{ action_id: 'recreate_static_nginx_container_with_mount', description: 'Recrear contenedor nginx' }],
  forbidden_actions: ['delete_client_files'],
};

const MOCK_VALIDATE_ALLOWED = {
  action_id: 'fix_import_tmp_permissions',
  allowed: true,
  reason: 'Action is registered as safe',
  requires_dry_run_first: true,
  requires_human_approval: false,
};

const MOCK_VALIDATE_DENIED = {
  action_id: 'delete_client_files',
  allowed: false,
  reason: 'Action is forbidden by policy',
  requires_dry_run_first: false,
  requires_human_approval: false,
};

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  listKnowledgeRunbooks.mockResolvedValue(MOCK_RUNBOOKS);
  getKnowledgeRunbook.mockResolvedValue(MOCK_RUNBOOK_DETAIL);
  matchKnowledgeIncident.mockResolvedValue(MOCK_MATCH);
  validateKnowledgeSafeAction.mockResolvedValue(MOCK_VALIDATE_ALLOWED);
  listKnowledgeSafeActions.mockResolvedValue(MOCK_SAFE_ACTIONS);
});

afterEach(() => {
  vi.clearAllMocks();
});

// ── Helper: switch to a tab ───────────────────────────────────────────────────

function clickTab(label) {
  const btn = screen.getAllByRole('button').find(b => b.textContent.includes(label));
  if (btn) fireEvent.click(btn);
}

// ── 1. renders search textarea ────────────────────────────────────────────────

describe('Search section', () => {
  it('renders search textarea', () => {
    render(<IncidentKnowledgePanel />);
    expect(screen.getByTestId('knowledge-search-textarea')).toBeInTheDocument();
  });

  // ── 2. search calls matchKnowledgeIncident with typed text ─────────────────

  it('search calls matchKnowledgeIncident with typed text', async () => {
    render(<IncidentKnowledgePanel />);
    const textarea = screen.getByTestId('knowledge-search-textarea');
    fireEvent.change(textarea, { target: { value: 'Welcome to nginx!' } });
    fireEvent.click(screen.getByTestId('knowledge-search-btn'));
    await waitFor(() => expect(matchKnowledgeIncident).toHaveBeenCalledWith('Welcome to nginx!', null));
  });

  // ── 3. match result shows incident_id ─────────────────────────────────────

  it('match result shows incident_id', async () => {
    render(<IncidentKnowledgePanel />);
    const textarea = screen.getByTestId('knowledge-search-textarea');
    fireEvent.change(textarea, { target: { value: 'some log text' } });
    fireEvent.click(screen.getByTestId('knowledge-search-btn'));
    await waitFor(() => expect(screen.getByTestId('knowledge-match-result')).toBeInTheDocument());
    expect(screen.getByTestId('knowledge-match-result').textContent).toContain('WELCOME_TO_NGINX_EMPTY_SITE');
  });

  // ── 4. match result shows safe_actions ────────────────────────────────────

  it('match result shows safe_actions chips', async () => {
    render(<IncidentKnowledgePanel />);
    fireEvent.change(screen.getByTestId('knowledge-search-textarea'), { target: { value: 'log' } });
    fireEvent.click(screen.getByTestId('knowledge-search-btn'));
    await waitFor(() => expect(screen.getByTestId('knowledge-match-result')).toBeInTheDocument());
    expect(screen.getByTestId('knowledge-match-result').textContent).toContain('recreate_static_nginx_container_with_mount');
  });

  // ── 5. match result shows forbidden_actions ───────────────────────────────

  it('match result shows forbidden_actions chips', async () => {
    render(<IncidentKnowledgePanel />);
    fireEvent.change(screen.getByTestId('knowledge-search-textarea'), { target: { value: 'log' } });
    fireEvent.click(screen.getByTestId('knowledge-search-btn'));
    await waitFor(() => expect(screen.getByTestId('knowledge-match-result')).toBeInTheDocument());
    expect(screen.getByTestId('knowledge-match-result').textContent).toContain('delete_client_files');
  });

  // ── 11. 401 response shows "No autenticado" ───────────────────────────────

  it('401 response shows "No autenticado"', async () => {
    matchKnowledgeIncident.mockRejectedValue({ response: { status: 401 } });
    render(<IncidentKnowledgePanel />);
    fireEvent.change(screen.getByTestId('knowledge-search-textarea'), { target: { value: 'log' } });
    fireEvent.click(screen.getByTestId('knowledge-search-btn'));
    await waitFor(() => expect(screen.getByText('No autenticado')).toBeInTheDocument());
  });

  // ── 12. backend error shows error message ─────────────────────────────────

  it('backend error shows error message', async () => {
    matchKnowledgeIncident.mockRejectedValue({ response: { data: { detail: 'Internal error' } } });
    render(<IncidentKnowledgePanel />);
    fireEvent.change(screen.getByTestId('knowledge-search-textarea'), { target: { value: 'log' } });
    fireEvent.click(screen.getByTestId('knowledge-search-btn'));
    await waitFor(() => expect(screen.getByText('Internal error')).toBeInTheDocument());
  });
});

// ── 6–8. Runbooks tab ─────────────────────────────────────────────────────────

describe('Runbooks section', () => {
  function renderAndSwitchToRunbooks() {
    render(<IncidentKnowledgePanel />);
    clickTab('Runbooks');
  }

  it('runbooks list renders on load with 2 rows', async () => {
    renderAndSwitchToRunbooks();
    await waitFor(() => {
      const rows = screen.getAllByTestId('knowledge-runbook-row');
      expect(rows).toHaveLength(2);
    });
  });

  // ── 7. runbook row click loads detail ─────────────────────────────────────

  it('runbook row click calls getKnowledgeRunbook with incident_id', async () => {
    renderAndSwitchToRunbooks();
    await waitFor(() => screen.getAllByTestId('knowledge-runbook-row'));
    const rows = screen.getAllByTestId('knowledge-runbook-row');
    fireEvent.click(rows[0]);
    await waitFor(() => expect(getKnowledgeRunbook).toHaveBeenCalledWith('WELCOME_TO_NGINX_EMPTY_SITE'));
  });

  // ── 8. runbook detail shows body ──────────────────────────────────────────

  it('runbook detail shows body text', async () => {
    renderAndSwitchToRunbooks();
    await waitFor(() => screen.getAllByTestId('knowledge-runbook-row'));
    fireEvent.click(screen.getAllByTestId('knowledge-runbook-row')[0]);
    await waitFor(() => expect(screen.getByTestId('knowledge-runbook-detail')).toBeInTheDocument());
    expect(screen.getByTestId('knowledge-runbook-detail').textContent).toContain('Síntoma: sitio muestra Welcome to nginx');
  });
});

// ── 9–10. Safe action validator tab ───────────────────────────────────────────

describe('Safe action validator section', () => {
  async function renderValidatorWithAction(mockResult) {
    validateKnowledgeSafeAction.mockResolvedValue(mockResult);
    render(<IncidentKnowledgePanel />);
    clickTab('Validar acción');
    // Wait for safe actions to load (renders as select)
    await waitFor(() => screen.getByTestId('knowledge-safe-action-select'));
    // Select action from dropdown populated by listKnowledgeSafeActions
    const select = screen.getByTestId('knowledge-safe-action-select');
    fireEvent.change(select, { target: { value: 'recreate_static_nginx_container_with_mount' } });
    fireEvent.click(screen.getByTestId('knowledge-safe-action-btn'));
    await waitFor(() => expect(screen.getByTestId('knowledge-safe-action-result')).toBeInTheDocument());
  }

  it('safe action validator shows allowed true (green badge)', async () => {
    await renderValidatorWithAction(MOCK_VALIDATE_ALLOWED);
    const result = screen.getByTestId('knowledge-safe-action-result');
    expect(result.textContent).toContain('Permitida');
    expect(result.textContent).toContain('Action is registered as safe');
  });

  it('safe action validator shows allowed false (red badge)', async () => {
    await renderValidatorWithAction(MOCK_VALIDATE_DENIED);
    const result = screen.getByTestId('knowledge-safe-action-result');
    expect(result.textContent).toContain('Denegada');
    expect(result.textContent).toContain('Action is forbidden by policy');
  });
});
