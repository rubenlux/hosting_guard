/**
 * Returns true if the event target is an element where the user expects
 * native text-editing shortcuts (Ctrl+C, Ctrl+V, etc.) to work.
 *
 * All global keyboard shortcut handlers MUST call this and bail out early
 * if it returns true, so clipboard and editing shortcuts keep working in
 * inputs, textareas, selects, and contentEditable nodes.
 */
export function isEditableTarget(target) {
  if (!target) return false;
  const tag = target.tagName;
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    target.isContentEditable === true
  );
}

/**
 * Returns true if the keyboard event is a clipboard or text-editing shortcut
 * (Ctrl/Cmd + C, V, X, A, Z).
 */
export function isClipboardShortcut(e) {
  if (!e.ctrlKey && !e.metaKey) return false;
  return ['c', 'v', 'x', 'a', 'z'].includes(e.key.toLowerCase());
}
