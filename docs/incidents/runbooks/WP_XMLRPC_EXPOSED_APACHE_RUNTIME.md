---
incident_id: WP_XMLRPC_EXPOSED_APACHE_RUNTIME
incident_type: security_vulnerability
severity: high
status: confirmed
validated: true
auto_repair_allowed: true
safe_actions:
  - block_xmlrpc_apache
forbidden_actions:
  - delete_xmlrpc_file_from_container
  - disable_wordpress_completely
  - auto_restart_wp_container
signatures:
  - "xmlrpc.php"
  - "200 OK.*xmlrpc"
  - "XML-RPC server accepts POST requests only"
---

# WP_XMLRPC_EXPOSED_APACHE_RUNTIME

## Síntoma
El endpoint `/xmlrpc.php` de un hosting WordPress es accesible públicamente y responde con HTTP 200. El escáner de seguridad detecta que la respuesta contiene el string `XML-RPC server accepts POST requests only`. El endpoint está siendo abusado para ataques de fuerza bruta de credenciales (método `system.multicall`) o para amplificación DDoS.

## Impacto
- **Alto riesgo de seguridad**: xmlrpc.php permite autenticación masiva en una sola petición (`system.multicall`), bypaseando los límites de intentos de login de WordPress.
- Potencial toma de control de la cuenta WordPress del cliente.
- Amplificación DDoS: el endpoint puede usarse como relay.
- Aumento de carga en el contenedor del cliente afectado.
- Si el cliente no usa Jetpack, WP mobile app, ni XML-RPC explícitamente, el endpoint es innecesario y debe bloquearse.

## Evidencia
```bash
# Desde el escáner o manualmente:
curl -s -o /dev/null -w "%{http_code}" https://cliente.hostingguard.example/xmlrpc.php
# Respuesta: 200

curl -s https://cliente.hostingguard.example/xmlrpc.php
# Respuesta: XML-RPC server accepts POST requests only.

# En logs de acceso nginx del contenedor:
grep "xmlrpc.php" /opt/clients/user_X_wordpress/logs/access.log | tail -20
# Múltiples POST de IPs externas con body XML
```

## Causa raíz
La configuración de nginx dentro del contenedor WordPress no incluye un bloque `location` que deniegue el acceso a `/xmlrpc.php`. WordPress incluye este archivo por defecto y Apache/nginx dentro del contenedor no lo bloquea. El template de configuración nginx para contenedores WordPress no contempló este bloqueo en su versión inicial.

## Diagnósticos equivocados
- **"El plugin de seguridad de WP lo gestiona"**: Los plugins de WordPress solo bloquean a nivel de PHP, después de que el servidor ya procesó la petición. La mitigación correcta es a nivel de servidor web (nginx).
- **"Solo afecta si el cliente tiene contraseña débil"**: xmlrpc permite millones de intentos en una sola petición HTTP vía `system.multicall`; la fortaleza de la contraseña no es suficiente protección.
- **"Basta con deshabilitar XML-RPC en WordPress"**: El filtro PHP de WP puede deshabilitarse desde plugins; el bloqueo en nginx es más robusto.

## Diagnóstico rápido
```bash
# 1. Verificar si xmlrpc.php responde 200
HOSTING_DOMAIN="cliente.hostingguard.example"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://${HOSTING_DOMAIN}/xmlrpc.php")
echo "xmlrpc.php HTTP status: ${HTTP_CODE}"
# 200 = vulnerable, 403 = bloqueado correctamente

# 2. Verificar configuración nginx del contenedor
CONTAINER_NAME="user_X_wordpress"
docker exec "${CONTAINER_NAME}" cat /etc/nginx/conf.d/wordpress.conf | grep -A5 "xmlrpc"

# 3. Ver logs de acceso para cuantificar el abuso
docker exec "${CONTAINER_NAME}" tail -50 /var/log/nginx/access.log | grep xmlrpc

# 4. Verificar si el template base incluye el bloqueo
grep -rn "xmlrpc" /opt/deploy/ 2>/dev/null || grep -rn "xmlrpc" app/templates/
```

## Solución manual
### Bloqueo inmediato en el contenedor afectado:
```bash
CONTAINER_NAME="user_X_wordpress"

# Añadir bloque de denegación en la configuración nginx del contenedor
docker exec "${CONTAINER_NAME}" bash -c 'cat >> /etc/nginx/conf.d/wordpress.conf << '"'"'EOF'"'"'

location = /xmlrpc.php {
    deny all;
    return 403;
}
EOF'

# Verificar sintaxis nginx
docker exec "${CONTAINER_NAME}" nginx -t

# Recargar nginx (sin restart del contenedor, sin downtime)
docker exec "${CONTAINER_NAME}" nginx -s reload

# Verificar que ahora retorna 403
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://${HOSTING_DOMAIN}/xmlrpc.php")
echo "xmlrpc.php HTTP status after fix: ${HTTP_CODE}"
# Debe ser 403
```

### Registrar el evento de seguridad:
```bash
# Emitir evento de seguridad en la plataforma para el hosting afectado
docker compose exec app python -c "
from app.services.security_service import emit_security_event
emit_security_event(
    hosting_id=X,
    event_type='xmlrpc_exposed',
    severity='high',
    details={'endpoint': '/xmlrpc.php', 'action': 'blocked'}
)
"
```

## Fix permanente
1. Actualizar el **template base de configuración nginx** para contenedores WordPress para incluir el bloqueo de `xmlrpc.php`:
   ```nginx
   # En el template: app/templates/nginx/wordpress.conf.j2
   location = /xmlrpc.php {
       deny all;
       return 403;
   }

   location = /wp-login.php {
       limit_req zone=wplogin burst=5 nodelay;
   }
   ```

2. Ejecutar un script de auditoría y parcheo masivo para todos los contenedores WordPress existentes:
   ```bash
   # Script: scripts/patch_xmlrpc_block.sh
   for container in $(docker ps --format "{{.Names}}" | grep "_wordpress"); do
       # Verificar si ya tiene el bloqueo
       if ! docker exec "$container" grep -q "xmlrpc" /etc/nginx/conf.d/wordpress.conf; then
           # Aplicar el fix
           docker exec "$container" bash -c '...'
           docker exec "$container" nginx -s reload
           echo "Patched: $container"
       fi
   done
   ```

3. Añadir comprobación periódica del escáner de seguridad para detectar `xmlrpc.php` expuesto.

## Señales para detección automática
- HTTP 200 en GET/POST a `*/xmlrpc.php`
- Response body contiene `XML-RPC server accepts POST requests only`
- Múltiples POST a `xmlrpc.php` desde IPs distintas (patrón de fuerza bruta)
- Pico de CPU en el contenedor WordPress asociado a peticiones xmlrpc

## Auto-remediation permitido
- `block_xmlrpc_apache`: Añadir un bloque `location = /xmlrpc.php { deny all; return 403; }` al nginx del contenedor y ejecutar `nginx -s reload`. Esta acción es segura: no modifica archivos de WordPress, no reinicia el contenedor, y es reversible.

## Auto-remediation prohibido
- `delete_xmlrpc_file_from_container`: Borrar `xmlrpc.php` del filesystem de WordPress rompe actualizaciones automáticas de WP. Además, el archivo puede recrearse en la próxima actualización de WP.
- `disable_wordpress_completely`: Detener el contenedor perjudica al cliente. El bloqueo de nginx es suficiente.
- `auto_restart_wp_container`: Un restart no resuelve el problema y causa downtime innecesario.

## Dashboard esperado
- **Security scanner**: `xmlrpc.php` retorna 403 en todos los contenedores WordPress.
- **Security Center**: evento `xmlrpc_exposed` registrado y resuelto para el hosting afectado.
- **Access logs**: no deben aparecer peticiones exitosas (200) a `xmlrpc.php`.
- **CPU del contenedor**: normalizado tras el bloqueo.

## RAG usage
Recuperar con: `xmlrpc.php exposed WordPress brute force`, `XML-RPC server accepts POST`, `nginx block xmlrpc WordPress container`.
Contexto relevante: templates nginx para contenedores WordPress, `app/services/security_service.py`, script de provisioning de contenedores.

## Tests/Chaos
```bash
# Test automático: verificar que xmlrpc.php retorna 403 en nuevos contenedores
# Después de provisionar un contenedor WordPress de prueba:
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://test-client.hostingguard.example/xmlrpc.php")
assert [ "$HTTP_CODE" = "403" ] || echo "FAIL: xmlrpc.php not blocked"

# Chaos: crear un contenedor WordPress sin el bloqueo y verificar que el escáner lo detecta
# El escáner de seguridad debe disparar alerta dentro de 1 ciclo de scan
```
