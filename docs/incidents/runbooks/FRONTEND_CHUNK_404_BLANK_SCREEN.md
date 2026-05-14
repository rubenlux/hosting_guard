---
incident_id: FRONTEND_CHUNK_404_BLANK_SCREEN
incident_type: frontend_deploy_issue
severity: high
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - clear_nginx_chunk_cache
forbidden_actions:
  - rollback_frontend_without_testing
  - auto_restart_all_sessions
signatures:
  - "Failed to fetch dynamically imported module"
  - "net::ERR_ABORTED 404"
  - "chunk.*404"
---

# FRONTEND_CHUNK_404_BLANK_SCREEN

## Síntoma
Tras un deploy del frontend de HostingGuard, algunos usuarios ven una pantalla en blanco. La consola del navegador muestra:
```
Failed to fetch dynamically imported module: https://app.hostingguard.example/assets/index-aBcD1234.js
net::ERR_ABORTED 404 (Not Found)
```
Los usuarios con tabs abiertas antes del deploy son los más afectados.

## Impacto
- **Alto**: pantalla en blanco para usuarios con sesiones activas previas al deploy.
- El frontend está completamente inoperativo para los usuarios afectados hasta que hacen hard refresh.
- Nuevos usuarios (o usuarios que refrescan) NO están afectados; cargan los nuevos chunks correctamente.
- No hay impacto en el backend, APIs, ni en los hostings de los clientes.
- Duración típica: el problema se auto-resuelve cuando el usuario cierra y reabre el tab.

## Evidencia
```
# Consola del navegador (DevTools → Console):
Failed to fetch dynamically imported module: /assets/index-aBcD1234.js
Uncaught (in promise) TypeError: Failed to import module script

# Network tab → /assets/index-aBcD1234.js → 404 Not Found

# En el servidor nginx que sirve el frontend:
# El archivo /assets/index-aBcD1234.js ya no existe (fue reemplazado por /assets/index-xYzW9876.js)
```

```bash
# Verificar qué chunks existen actualmente en el servidor:
docker exec traefik ls /frontend/assets/ | grep index
# index-xYzW9876.js  ← nuevo chunk (existe)
# index-aBcD1234.js  ← antiguo chunk (ya no existe)
```

## Causa raíz
Vite (el bundler del frontend de HostingGuard) genera nombres de archivo con hash de contenido (`index-XXXXXXXX.js`). Cada build produce hashes distintos.

Flujo del problema:
1. Usuario carga el frontend → navegador descarga `index.html` con referencia a `index-aBcD1234.js`.
2. Se hace deploy de una nueva versión → `index.html` ahora referencia `index-xYzW9876.js`.
3. El usuario mantiene el tab abierto → su `index.html` (cacheado o en memoria) sigue referenciando el chunk antiguo.
4. El usuario navega a otra ruta → React Router carga un chunk lazy → intenta descargar `index-aBcD1234.js` → 404.
5. El módulo no se puede cargar → pantalla en blanco.

Este es el comportamiento esperado de Vite con code splitting y lazy routes. La solución es controlar los cache headers del `index.html` para que no se cachee más allá del deploy.

## Diagnósticos equivocados
- **"El build de Vite falló"**: Los chunks existen; solo los chunks de la versión anterior ya no están.
- **"Error de nginx"**: Nginx sirve correctamente lo que tiene; el problema es que el chunk solicitado ya no existe.
- **"Bug en el código del frontend"**: Es un comportamiento inherente al hash de contenido de Vite, no un bug de código.
- **"El CDN está cacheando mal"**: Si no hay CDN, el problema es solo en el tab del usuario. Con CDN, verificar invalidación de caché.
- **"Todos los usuarios están afectados"**: Solo los usuarios con tabs abiertos ANTES del deploy.

## Diagnóstico rápido
```bash
# 1. Confirmar que el deploy fue reciente
docker compose logs app --tail=5 | grep -i "deploy\|frontend"

# 2. Verificar que los assets nuevos existen y los antiguos no
ls /frontend/dist/assets/ | grep "index-"
# Debe haber UN solo index-XXXXX.js (el del último build)

# 3. Verificar headers de caché del index.html
curl -I https://app.hostingguard.example/ | grep -i "cache-control\|etag\|last-modified"

# 4. Verificar que la 404 es por el chunk antiguo y no por un error de build
# El chunk que da 404 debe tener un hash DISTINTO al que existe actualmente en /assets/
```

## Solución manual
### Para usuarios afectados:
Instruir a los usuarios que hagan **hard refresh**: `Ctrl+Shift+R` (Windows/Linux) o `Cmd+Shift+R` (Mac).

O en el panel de soporte: comunicar por banner/notificación en app que deben refrescar si ven pantalla en blanco.

### Acción en servidor: limpiar caché de nginx para index.html
```bash
# Si nginx tiene proxy_cache configurado para el frontend:
docker exec nginx nginx -s reload  # invalida el cache en memory
# O si el cache es en disco:
docker exec nginx find /var/cache/nginx/ -name "*.cache" -delete
# Luego reload:
docker exec nginx nginx -s reload
```

### Si hay CDN (CloudFlare, etc.):
Purgar el caché del CDN para `/index.html` e `/*` tras cada deploy.

## Fix permanente
### 1. Configurar Cache-Control correcto para `index.html`:
```nginx
# En la config nginx del frontend:
location = /index.html {
    # NUNCA cachear el index.html; siempre servir la versión más reciente
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    add_header Pragma "no-cache";
    add_header Expires "0";
}

location /assets/ {
    # Los assets tienen hash en el nombre → cachear agresivamente
    add_header Cache-Control "public, max-age=31536000, immutable";
}
```

### 2. Manejo de error de chunk en el frontend:
```typescript
// En el router de React (main.tsx o router.tsx):
// Detectar error de chunk load y forzar recarga
window.addEventListener('unhandledrejection', (event) => {
  if (
    event.reason?.message?.includes('Failed to fetch dynamically imported module') ||
    event.reason?.message?.includes('Loading chunk')
  ) {
    console.warn('Chunk load failed — new deploy detected. Reloading...');
    // Recargar una sola vez para obtener el nuevo index.html
    if (!sessionStorage.getItem('chunk_reload_attempted')) {
      sessionStorage.setItem('chunk_reload_attempted', 'true');
      window.location.reload();
    } else {
      sessionStorage.removeItem('chunk_reload_attempted');
      // Mostrar mensaje de error al usuario si ya se intentó reload
    }
  }
});
```

### 3. Script de deploy con invalidación de caché automática:
```bash
# Al final del deploy del frontend:
# 1. Build Vite
npm run build

# 2. Copiar dist/ al servidor
rsync -av dist/ /frontend/dist/

# 3. Invalidar caché de nginx para index.html
docker exec nginx nginx -s reload
echo "Frontend deployed. Cache invalidated."
```

## Señales para detección automática
- Pico de errores 404 en `/assets/*.js` justo después de un deploy
- Tasa de errores `Failed to fetch dynamically imported module` en Sentry/logs
- Múltiples peticiones a un mismo chunk hash que ya no existe en el servidor

## Auto-remediation permitido
- `clear_nginx_chunk_cache`: Ejecutar `nginx -s reload` en el contenedor del frontend para limpiar el cache en memoria. Es seguro y no causa downtime (nginx recarga en caliente).

## Auto-remediation prohibido
- `rollback_frontend_without_testing`: Un rollback sin testing puede restaurar bugs corregidos. Primero verificar que el problema no se soluciona con hard refresh.
- `auto_restart_all_sessions`: Invalidar todas las sesiones de usuario (forzar logout) es una intervención desproporcionada para este problema.

## Dashboard esperado
- **404 rate en /assets/**: < 0.1% en condiciones normales. Pico post-deploy debe bajar a 0 en < 5 min (usuarios refrescando).
- **index.html Cache-Control**: `no-cache, no-store, must-revalidate` (verificar con curl -I).
- **/assets/ Cache-Control**: `public, max-age=31536000, immutable`.
- **Sentry/error tracking**: 0 errores `Failed to fetch dynamically imported module` más de 10 minutos después del deploy.

## RAG usage
Recuperar con: `chunk 404 blank screen Vite deploy`, `Failed to fetch dynamically imported module frontend`, `cache-control index.html Vite frontend deploy`.
Contexto relevante: configuración nginx del frontend, proceso de deploy del frontend, `vite.config.ts`.

## Tests/Chaos
```bash
# Test de headers de caché:
# index.html debe tener no-cache
HTTP_CACHE=$(curl -sI https://app.hostingguard.example/ | grep -i cache-control)
echo "index.html Cache-Control: ${HTTP_CACHE}"
# Debe incluir 'no-cache' o 'no-store'

# Assets deben tener cache largo
ASSET_CACHE=$(curl -sI "https://app.hostingguard.example/assets/index-$(ls /frontend/dist/assets/ | grep index | head -1)" | grep -i cache-control)
echo "asset Cache-Control: ${ASSET_CACHE}"
# Debe incluir 'max-age=31536000'

# Chaos: deploy una nueva versión y abrir el antiguo index.html en un tab
# Verificar que el manejador de error de chunk fuerza reload automáticamente
```
