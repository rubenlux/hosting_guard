/**
 * Tests for keyboard utility — isEditableTarget / isClipboardShortcut.
 *
 * Ensures global keyboard handlers never intercept clipboard shortcuts
 * when focus is on an editable element (input, textarea, select, contentEditable).
 */
import { describe, it, expect } from 'vitest';
import { isEditableTarget, isClipboardShortcut } from './keyboard';

// ── isEditableTarget ──────────────────────────────────────────────────────────

describe('isEditableTarget', () => {
  it('returns true for TEXTAREA', () => {
    expect(isEditableTarget({ tagName: 'TEXTAREA' })).toBe(true);
  });

  it('returns true for INPUT', () => {
    expect(isEditableTarget({ tagName: 'INPUT' })).toBe(true);
  });

  it('returns true for SELECT', () => {
    expect(isEditableTarget({ tagName: 'SELECT' })).toBe(true);
  });

  it('returns true for contentEditable element', () => {
    expect(isEditableTarget({ tagName: 'DIV', isContentEditable: true })).toBe(true);
  });

  it('returns false for BUTTON', () => {
    expect(isEditableTarget({ tagName: 'BUTTON' })).toBe(false);
  });

  it('returns false for DIV (non-editable)', () => {
    expect(isEditableTarget({ tagName: 'DIV', isContentEditable: false })).toBe(false);
  });

  it('returns false for null', () => {
    expect(isEditableTarget(null)).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(isEditableTarget(undefined)).toBe(false);
  });
});

// ── isClipboardShortcut ───────────────────────────────────────────────────────

describe('isClipboardShortcut', () => {
  const ctrl = (key) => ({ ctrlKey: true, metaKey: false, key });
  const meta = (key) => ({ ctrlKey: false, metaKey: true, key });
  const plain = (key) => ({ ctrlKey: false, metaKey: false, key });

  it('returns true for Ctrl+C', () => {
    expect(isClipboardShortcut(ctrl('c'))).toBe(true);
  });

  it('returns true for Ctrl+V', () => {
    expect(isClipboardShortcut(ctrl('v'))).toBe(true);
  });

  it('returns true for Ctrl+X', () => {
    expect(isClipboardShortcut(ctrl('x'))).toBe(true);
  });

  it('returns true for Ctrl+A', () => {
    expect(isClipboardShortcut(ctrl('a'))).toBe(true);
  });

  it('returns true for Ctrl+Z', () => {
    expect(isClipboardShortcut(ctrl('z'))).toBe(true);
  });

  it('returns true for Cmd+C (macOS)', () => {
    expect(isClipboardShortcut(meta('c'))).toBe(true);
  });

  it('returns true for Cmd+V (macOS)', () => {
    expect(isClipboardShortcut(meta('v'))).toBe(true);
  });

  it('returns false for Ctrl+S (save shortcut — not clipboard)', () => {
    expect(isClipboardShortcut(ctrl('s'))).toBe(false);
  });

  it('returns false for plain V key (no modifier)', () => {
    expect(isClipboardShortcut(plain('v'))).toBe(false);
  });
});

// ── Global shortcut guard contract ───────────────────────────────────────────

describe('global shortcut guard contract', () => {
  it('isEditableTarget + isClipboardShortcut: should bail on Ctrl+V in textarea', () => {
    const target = { tagName: 'TEXTAREA' };
    const e = { ctrlKey: true, metaKey: false, key: 'v', target };
    const shouldBail = isEditableTarget(e.target) && isClipboardShortcut(e);
    expect(shouldBail).toBe(true);
  });

  it('isEditableTarget + isClipboardShortcut: should bail on Ctrl+C in input', () => {
    const target = { tagName: 'INPUT' };
    const e = { ctrlKey: true, metaKey: false, key: 'c', target };
    expect(isEditableTarget(e.target) && isClipboardShortcut(e)).toBe(true);
  });

  it('global shortcut fires normally outside editable elements (Ctrl+S on div)', () => {
    const target = { tagName: 'DIV', isContentEditable: false };
    const e = { ctrlKey: true, metaKey: false, key: 's', target };
    const shouldBail = isEditableTarget(e.target) && isClipboardShortcut(e);
    expect(shouldBail).toBe(false);
  });

  it('Ctrl+V in textarea must not trigger preventDefault in guarded handler', () => {
    const prevented = [];
    const target = { tagName: 'TEXTAREA' };
    const e = {
      ctrlKey: true, metaKey: false, key: 'v', target,
      preventDefault: () => prevented.push('v'),
    };

    // Simulate the guarded handler pattern used in FileManager and any global handler
    function guardedHandler(event) {
      if (isEditableTarget(event.target) && isClipboardShortcut(event)) return;
      event.preventDefault();
    }

    guardedHandler(e);
    expect(prevented).toHaveLength(0);
  });

  it('Ctrl+C in textarea must not trigger preventDefault', () => {
    const prevented = [];
    const target = { tagName: 'TEXTAREA' };
    const e = {
      ctrlKey: true, metaKey: false, key: 'c', target,
      preventDefault: () => prevented.push('c'),
    };

    function guardedHandler(event) {
      if (isEditableTarget(event.target) && isClipboardShortcut(event)) return;
      event.preventDefault();
    }

    guardedHandler(e);
    expect(prevented).toHaveLength(0);
  });
});
