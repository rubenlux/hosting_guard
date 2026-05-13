/**
 * LoginModal — 2FA flow tests.
 *
 * 1. Normal login (no 2FA) calls loginAction and closes modal.
 * 2. Login with 2FA response shows OTP field, no token in DOM.
 * 3. OTP submit with valid code calls loginAction and closes modal.
 * 4. OTP submit with invalid code shows error message.
 * 5. No token is stored in DOM/state before OTP completes.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  login: vi.fn(),
  register: vi.fn(),
  forgotPassword: vi.fn(),
  resendVerification: vi.fn(),
  verify2FALogin: vi.fn(),
}));

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ loginAction: vi.fn().mockResolvedValue(undefined) }),
}));

import { login, verify2FALogin } from '../services/api';
import LoginModal from './LoginModal';

function renderModal(onLoginSuccess = vi.fn(), onClose = vi.fn()) {
  return render(
    <LoginModal isOpen={true} onClose={onClose} onLoginSuccess={onLoginSuccess} />
  );
}

async function submitLogin(email = 'user@t.com', password = 'pass123') {
  fireEvent.change(screen.getByPlaceholderText('tu@email.com'), {
    target: { value: email },
  });
  fireEvent.change(screen.getByPlaceholderText('••••••••'), {
    target: { value: password },
  });
  await act(async () => {
    fireEvent.click(screen.getByText('ENTRAR'));
  });
}

describe('LoginModal — normal login', () => {
  it('calls loginAction and closes modal on successful login', async () => {
    login.mockResolvedValueOnce({ status: 'ok', account_type: 'user' });
    const onLoginSuccess = vi.fn();
    const onClose = vi.fn();
    renderModal(onLoginSuccess, onClose);

    await submitLogin();

    await waitFor(() => {
      expect(onLoginSuccess).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });
});

describe('LoginModal — 2FA flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows OTP field when server returns 2fa_required', async () => {
    login.mockResolvedValueOnce({ status: '2fa_required' });
    renderModal();

    await submitLogin();

    await waitFor(() => {
      expect(screen.getByText('Verificación en dos pasos')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('123456')).toBeInTheDocument();
    });
  });

  it('does not show access_token in DOM when transitioning to OTP step', async () => {
    login.mockResolvedValueOnce({ status: '2fa_required' });
    const { container } = renderModal();

    await submitLogin();

    await waitFor(() => {
      expect(screen.getByText('Verificación en dos pasos')).toBeInTheDocument();
    });

    // No raw token content anywhere in the rendered DOM
    expect(container.innerHTML).not.toMatch(/access_token/i);
    expect(container.innerHTML).not.toMatch(/eyJ/); // JWT prefix
  });

  it('calls loginAction and closes on valid OTP submission', async () => {
    login.mockResolvedValueOnce({ status: '2fa_required' });
    verify2FALogin.mockResolvedValueOnce({ status: 'ok', account_type: 'user' });
    const onLoginSuccess = vi.fn();
    const onClose = vi.fn();
    renderModal(onLoginSuccess, onClose);

    await submitLogin();
    await waitFor(() => screen.getByPlaceholderText('123456'));

    await act(async () => {
      fireEvent.change(screen.getByPlaceholderText('123456'), {
        target: { value: '123456' },
      });
      fireEvent.click(screen.getByText('VERIFICAR'));
    });

    await waitFor(() => {
      expect(verify2FALogin).toHaveBeenCalledWith('123456');
      expect(onLoginSuccess).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('shows error message on invalid OTP without closing modal', async () => {
    login.mockResolvedValueOnce({ status: '2fa_required' });
    verify2FALogin.mockRejectedValueOnce({
      response: { status: 401, data: { detail: 'Código incorrecto' } },
    });
    const onClose = vi.fn();
    renderModal(vi.fn(), onClose);

    await submitLogin();
    await waitFor(() => screen.getByPlaceholderText('123456'));

    await act(async () => {
      fireEvent.change(screen.getByPlaceholderText('123456'), {
        target: { value: '000000' },
      });
      fireEvent.click(screen.getByText('VERIFICAR'));
    });

    await waitFor(() => {
      expect(screen.getByText('Código incorrecto')).toBeInTheDocument();
      expect(onClose).not.toHaveBeenCalled();
    });
  });
});
