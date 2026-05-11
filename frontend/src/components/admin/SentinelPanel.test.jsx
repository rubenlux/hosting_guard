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
}));

import {
  getSentinelIncidents, triggerDiagnose, getDiagnosis,
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
