/**
 * StatusCommandBar tests.
 *
 * Critical: must NOT show "Todo operativo" when any active hosting has
 * public_reachable=false in healthData (403 nginx, 526 CF, missing route, etc.)
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import StatusCommandBar from './StatusCommandBar';

const HOSTING_ACTIVE = { hosting_id: 1, status: 'active' };
const HOSTING_INACTIVE = { hosting_id: 2, status: 'inactive' };

describe('StatusCommandBar health label', () => {
  it('shows "Todo operativo" when all routes healthy', () => {
    const healthData = { 1: { score: 90, public_reachable: true } };
    render(
      <StatusCommandBar
        hostings={[HOSTING_ACTIVE]}
        healthData={healthData}
        advisories={[]}
        alerts={[]}
      />,
    );
    expect(screen.getByText('Todo operativo')).toBeInTheDocument();
  });

  it('shows degraded label when tenant has public_reachable=false (403 nginx)', () => {
    const healthData = { 1: { score: 0, public_reachable: false, router_incident_type: 'nginx_403_empty_index' } };
    render(
      <StatusCommandBar
        hostings={[HOSTING_ACTIVE]}
        healthData={healthData}
        advisories={[]}
        alerts={[]}
      />,
    );
    expect(screen.queryByText('Todo operativo')).not.toBeInTheDocument();
    expect(screen.getByText(/ruta caída/)).toBeInTheDocument();
  });

  it('shows degraded label when tenant has public_reachable=false (526 CF)', () => {
    const healthData = { 1: { score: 0, public_reachable: false, router_incident_type: 'cloudflare_526_origin_tls' } };
    render(
      <StatusCommandBar
        hostings={[HOSTING_ACTIVE]}
        healthData={healthData}
        advisories={[]}
        alerts={[]}
      />,
    );
    expect(screen.queryByText('Todo operativo')).not.toBeInTheDocument();
  });

  it('container running alone does not make status "Todo operativo" if route is broken', () => {
    // Simulate: container_running=true but public_reachable=false
    const healthData = { 1: { score: 0, public_reachable: false } };
    render(
      <StatusCommandBar
        hostings={[HOSTING_ACTIVE]}
        healthData={healthData}
        advisories={[]}
        alerts={[]}
      />,
    );
    expect(screen.queryByText('Todo operativo')).not.toBeInTheDocument();
    expect(screen.getByText(/ruta caída/)).toBeInTheDocument();
  });

  it('inactive hosting does not affect health label', () => {
    const healthData = { 2: { score: 0, public_reachable: false } };
    render(
      <StatusCommandBar
        hostings={[HOSTING_INACTIVE]}
        healthData={healthData}
        advisories={[]}
        alerts={[]}
      />,
    );
    // Inactive hosting not counted — all ok
    expect(screen.getByText('Todo operativo')).toBeInTheDocument();
  });

  it('shows critical advisory label when advisories passed', () => {
    const healthData = { 1: { score: 90, public_reachable: true } };
    const advisories = [{ severity: 'critical' }];
    render(
      <StatusCommandBar
        hostings={[HOSTING_ACTIVE]}
        healthData={healthData}
        advisories={advisories}
        alerts={[]}
      />,
    );
    expect(screen.queryByText('Todo operativo')).not.toBeInTheDocument();
    expect(screen.getByText(/alerta crítica/)).toBeInTheDocument();
  });

  it('shows broken routes count when multiple tenants have route issues', () => {
    const HOSTING_2 = { hosting_id: 2, status: 'active' };
    const healthData = {
      1: { score: 0, public_reachable: false },
      2: { score: 0, public_reachable: false },
    };
    render(
      <StatusCommandBar
        hostings={[HOSTING_ACTIVE, HOSTING_2]}
        healthData={healthData}
        advisories={[]}
        alerts={[]}
      />,
    );
    expect(screen.getByText(/2 sitios con ruta caída/)).toBeInTheDocument();
  });
});
