---
incident_id: TENANT_ROUTE_DOCKER_LABELS_ONLY
incident_type: routing
severity: high
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - regenerate_tenant_file_provider_route
  - migrate_tenant_route_docker_labels_to_file
  - validate_traefik_dynamic_yaml
  - verify_forwardauth_file_middleware
forbidden_actions:
  - rely_on_docker_provider_only
  - bypass_forwardauth
  - mark_healthy_without_file_provider_route
  - disable_router_health_check
signatures:
  - "router_source docker_labels"
  - "no dynamic file route found"
  - "missing tenant File Provider YAML"
  - "tenant route depends on Docker labels"
  - "traefik labels only"
  - "tenant_route_docker_labels_only"
  - "File Provider YAML missing"
---

# TENANT_ROUTE_DOCKER_LABELS_ONLY

## Síntoma

El Router Health Guard detecta que el tenant `{hosting_id}` no tiene un archivo
`/opt/traefik-dynamic/tenant-{hosting_id}.yml`. El routing de Traefik depende
exclusivamente de las Docker labels del contenedor (`traefik.enable=true`, etc.).

El sitio puede estar accesible en este momento, pero está en estado degradado:
cualquier reinicio del Docker provider, actualización de Traefik, o mismatch de
versión del socket proxy dejará al tenant inaccesible sin File Provider YAML.

## Impacto

- **Inmediato:** El tenant sigue accesible mientras el Docker provider funcione.
- **Latente:** Si el Docker provider falla (ver `TRAEFIK_DOCKER_PROVIDER_UNHEALTHY`),
  este tenant no tiene fallback — queda sin ruta.
- **ForwardAuth:** Si el ForwardAuth también se define solo vía Docker label
  (`hg-forwardauth@docker`), y el Docker provider cae, la autenticación se rompe.
- **Provisioning Gate:** El Gate marcó el tenant como `routing_degraded` en creación.
  Esta degradación persiste hasta que se genere el YAML.

## Causa raíz

La causa más común es que `create_hosting` no generó el archivo YAML (fallo en
`create_tenant_file_provider`) o el archivo fue eliminado sin pasar por
`delete_tenant_file_provider`.

Causas secundarias:
- El directorio `/opt/traefik-dynamic` no estaba montado en `rw` en el contenedor
  de la app al momento de la creación.
- El tenant fue creado en una versión anterior de HostingGuard que no tenía el
  File Provider.
- El archivo fue borrado manualmente o por un script de limpieza no autorizado.

## Diagnóstico

```bash
# 1. Verificar si existe el YAML del tenant
ls -la /opt/traefik-dynamic/tenant-{hosting_id}.yml

# 2. Confirmar el router_source del tenant via API
curl -s http://localhost:8000/admin/router-health/tenants?hosting_id={hosting_id} | jq .

# 3. Ver las labels del contenedor (confirmar que Docker labels están)
docker inspect --format '{{json .Config.Labels}}' {container_name} | jq .

# 4. Verificar que Traefik lee el directorio dinámico
ls -la /opt/traefik-dynamic/

# 5. Verificar que el directorio es montado RW en el contenedor app
docker inspect hosting_guard --format '{{json .Mounts}}' | jq '.[] | select(.Destination == "/opt/traefik-dynamic")'
```

## Remediación

### Opción A — Reparación desde el panel de admin (recomendada)

1. Ir a **Admin → Router Health → Tenants**.
2. Buscar el tenant por `hosting_id` o dominio.
3. Hacer clic en **"Simular reparación"** (dry_run) — confirmar que el YAML generado es correcto.
4. Hacer clic en **"Aplicar reparación"** — esto llama a `ensure_tenant_traefik_route(hosting_id, dry_run=False)`.
5. Verificar que `router_source` cambia a `dynamic_file` en la siguiente comprobación.

### Opción B — Reparación desde el host

```bash
# Generar el YAML directamente en el host (no requiere que el contenedor app esté RW)
HOSTING_ID={hosting_id}
CONTAINER={container_name}
SUBDOMAIN={subdomain}

cat > /opt/traefik-dynamic/tenant-${HOSTING_ID}.yml << EOF
# tenant-${HOSTING_ID}.yml
# Regenerated manually — TENANT_ROUTE_DOCKER_LABELS_ONLY incident
http:
  routers:
    tenant-${HOSTING_ID}:
      rule: "Host(\`${SUBDOMAIN}\`)"
      entryPoints:
        - websecure
      service: tenant-${HOSTING_ID}
      tls:
        certResolver: le
      middlewares:
        - hg-forwardauth@file
      priority: 50

  services:
    tenant-${HOSTING_ID}:
      loadBalancer:
        servers:
          - url: "http://${CONTAINER}:80"
EOF

# Verificar que Traefik lo cargó (sin reiniciar)
curl -s http://traefik:8080/api/http/routers | jq '.[] | select(.name | contains("tenant-'${HOSTING_ID}'")'
```

### Validación post-remediación

```bash
# 1. Confirmar que el YAML existe
ls -la /opt/traefik-dynamic/tenant-{hosting_id}.yml

# 2. Confirmar que el router health guard detecta dynamic_file
curl -s http://localhost:8000/admin/router-health/tenants?hosting_id={hosting_id} | jq '.[] | .router_source'
# Debe devolver: "dynamic_file"

# 3. Confirmar que el sitio responde con ForwardAuth activo
curl -I https://{subdomain}/
# Debe devolver 302 (redirect to login) o 401 — NO debe devolver 404 o 526
```

## Prevención

- `create_hosting` siempre llama a `create_tenant_file_provider` — verificar logs si falla.
- `_do_delete_hosting` llama a `delete_tenant_file_provider` — el YAML se borra con el tenant.
- El Router Health Guard tiene `routing_degraded` en su query de tenants monitoreados —
  este incident se crea automáticamente en el siguiente ciclo.
- El Provisioning Gate en `create_hosting` detecta `routing_degraded` y lo registra
  como audit event `hosting.provisioning.gate_failed`.

## Acciones prohibidas

| Acción prohibida | Por qué |
|---|---|
| `rely_on_docker_provider_only` | Si el Docker provider cae, el tenant queda sin ruta. No hay fallback. |
| `bypass_forwardauth` | Sin `hg-forwardauth@file`, el tenant es accesible sin autenticación. |
| `mark_healthy_without_file_provider_route` | Encubre el riesgo de routing_degraded. |
| `disable_router_health_check` | Sin el guard, este incident no se detecta hasta que el sitio cae. |

## Chaos test

```bash
# 1. Crear tenant de prueba
# 2. Borrar su YAML manualmente
rm /opt/traefik-dynamic/tenant-{test_hosting_id}.yml
# 3. Forzar corrida del Router Health Guard
curl -X POST http://localhost:8000/admin/router-health/tenants/check -H "Authorization: Bearer $TOKEN"
# 4. Verificar que se creó el incident TENANT_ROUTE_DOCKER_LABELS_ONLY
# 5. Reparar vía API y verificar resolución del incident
```
