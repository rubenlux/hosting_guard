// Los tokens ya NO se almacenan en localStorage.
// Las cookies HttpOnly son gestionadas automáticamente por el navegador.
// Este módulo se mantiene para compatibilidad pero no expone tokens al JS.

// isLoggedIn() ya no es fiable desde el cliente: la cookie HttpOnly
// es invisible para JS. El estado de autenticación viene de /me via useAuth.
export const isLoggedIn = () => false; // siempre false; usar useAuth().user en su lugar
