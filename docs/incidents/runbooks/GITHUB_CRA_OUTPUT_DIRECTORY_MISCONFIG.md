---
incident_id: GITHUB_CRA_OUTPUT_DIRECTORY_MISCONFIG
incident_type: deploy_misconfiguration
severity: medium
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions: []
forbidden_actions:
  - publish_public_directory_as_cra_output
  - auto_change_output_dir_without_user_confirmation
signatures:
  - "Failed to fetch dynamically imported module"
  - "Cannot GET /"
  - "output directory not found"
---

# GITHUB_CRA_OUTPUT_DIRECTORY_MISCONFIG

## Síntoma
Un sitio desplegado desde GitHub usando Create React App (CRA) muestra una página en blanco o un error 404 para todos los assets tras el deploy. El navegador muestra `Cannot GET /` o `Failed to fetch dynamically imported module`. El deploy aparece como exitoso en los logs.

## Impacto
- El sitio del cliente está completamente caído (blank page o 404).
- Solo afecta a sitios CRA con directorio de salida mal configurado.
- Otros hostings no se ven afectados.
- El cliente puede reportarlo como "el deploy destruyó mi sitio".
- No hay pérdida de datos; los archivos del build están en el servidor, solo en el directorio incorrecto.

## Evidencia
```bash
# En el contenedor nginx del hosting estático:
docker exec user_X_nginx ls /var/www/html/
# Aparece vacío o solo archivos de build intermedios

# Verificar qué directorio se copió realmente
docker exec user_X_nginx ls /var/www/html/build/ 2>/dev/null || echo "build/ not found"
docker exec user_X_nginx ls /var/www/html/public/ 2>/dev/null || echo "public/ not found"

# En logs del worker ARQ durante el import:
docker compose logs hg_worker | grep "output directory\|No such file\|build\|public"
```

```
FileNotFoundError: output directory 'build/' not found in repository
# o bien el directorio se copió pero estaba vacío:
WARNING: output directory 'public/' is empty, deploy may be incorrect
```

## Causa raíz
Create React App produce su output en `build/` por defecto. Sin embargo:

1. El cliente configuró en HostingGuard el directorio de salida como `public/` (confundiéndolo con la carpeta `public/` de fuentes de CRA, que contiene solo el `index.html` plantilla).
2. O bien: la plataforma tiene un valor por defecto incorrecto para proyectos CRA (`public/` en lugar de `build/`).
3. O bien: el repositorio usa una configuración de CRA custom que sí genera en `public/`, y el deploy asume `build/`.

La confusión es frecuente porque CRA tiene una carpeta `public/` de **fuentes** (assets estáticos como favicon, index.html plantilla) y una carpeta `build/` de **output** (el resultado del `npm run build`). Son cosas distintas.

Frameworks afectados:
- Create React App: output en `build/`
- Vite (React): output en `dist/`
- Next.js static export: output en `out/`
- Gatsby: output en `public/` (aquí sí es `public/`)

## Diagnósticos equivocados
- **"El build de CRA falló"**: El build puede haber completado correctamente; el error es en qué directorio se desplegó.
- **"Problema de permisos en el contenedor nginx"**: Si el directorio está vacío o es incorrecto, el problema es de configuración de deploy, no de permisos.
- **"CRA no es compatible con HostingGuard"**: CRA es compatible; solo hay que usar `build/` como output dir.
- **"El repositorio GitHub tiene un error"**: El repositorio puede estar correcto; el error es en la config de deploy de HostingGuard.

## Diagnóstico rápido
```bash
# 1. Verificar qué directorio de output está configurado para el hosting
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"SELECT id, output_directory, github_repo FROM hostings WHERE id=X\"))
for row in result: print(row)
"

# 2. Verificar el contenido actual del webroot del contenedor
docker exec user_X_nginx find /var/www/html -maxdepth 2 -type f | head -20

# 3. Clonar el repo y verificar qué genera el build
# (en un entorno de test, no en producción)
git clone https://github.com/cliente/repo /tmp/test_repo
cd /tmp/test_repo && npm install && npm run build
ls -la /tmp/test_repo/  # ¿build/ o public/ o dist/?
```

## Solución manual
**IMPORTANTE**: No cambiar el directorio de output automáticamente. Requiere confirmación del cliente.

### Pasos:
1. Identificar el directorio de output correcto del proyecto del cliente:
   - Si usa CRA estándar: `build/`
   - Si usa Vite: `dist/`
   - Si usa Gatsby: `public/`
   - Si usa Next.js export: `out/`

2. Comunicar al cliente que debe actualizar la configuración en HostingGuard:
   ```
   "Tu proyecto parece ser Create React App. El directorio de salida correcto es 'build/'.
    Por favor actualiza la configuración en tu panel a 'build/' y haz un nuevo deploy."
   ```

3. Una vez confirmado por el cliente, actualizar en la plataforma y redesplegar:
   ```bash
   # Si el admin actualiza la config por el cliente:
   docker compose exec app python -c "
   from app.db.session import get_db
   from sqlalchemy import text
   db = next(get_db())
   db.execute(text(\"UPDATE hostings SET output_directory='build' WHERE id=X\"))
   db.commit()
   "
   # Disparar un nuevo deploy desde GitHub
   ```

## Fix permanente
1. Añadir **detección automática del framework** en el import pipeline:
   - Si se detecta `react-scripts` en `package.json` → sugerir `build/` como output dir.
   - Si se detecta `vite` → sugerir `dist/`.
   - Mostrar la sugerencia en el onboarding del deploy.

2. Añadir validación en el pipeline de deploy: antes de copiar, verificar que el directorio de output existe y no está vacío. Si falla, abortar el deploy con error claro en lugar de desplegar un sitio vacío.

3. Documentar los directorios de output por framework en la UI de configuración de deploy.

4. Añadir smoke test post-deploy: verificar que `index.html` existe en el webroot y que responde 200.

## Señales para detección automática
- HTTP 404 en `/` del hosting tras un deploy desde GitHub
- `Cannot GET /` en el cuerpo de la respuesta del hosting
- `output directory not found` en logs del worker ARQ
- Directorio `/var/www/html` vacío o sin `index.html` tras el deploy

## Auto-remediation permitido
Ninguna. Cambiar el directorio de output es una decisión que requiere confirmación explícita del cliente o del administrador. Un cambio automático podría desplegar el directorio incorrecto.

## Auto-remediation prohibido
- `publish_public_directory_as_cra_output`: Publicar `public/` como si fuera el output de CRA desplegará solo los assets de fuente (favicon, index.html sin bundle) en lugar del sitio compilado.
- `auto_change_output_dir_without_user_confirmation`: Cambiar la configuración del directorio de output sin confirmación puede romper proyectos que sí usan `public/` como output (como Gatsby).

## Dashboard esperado
- **Deploy status**: éxito solo cuando `index.html` existe en el webroot y el sitio responde 200.
- **Deploy logs**: mensaje claro si el directorio de output configurado no existe en el repo.
- **Smoke test**: resultado de la comprobación post-deploy visible en el historial de deploys.

## RAG usage
Recuperar con: `CRA output directory build public blank page`, `Create React App deploy wrong directory`, `output directory not found GitHub deploy`.
Contexto relevante: pipeline de import/deploy en ARQ worker, configuración `output_directory` en modelo `Hosting`, template nginx para sitios estáticos.

## Tests/Chaos
```python
# Test: deploy con output_directory='public/' en un repo CRA (que genera 'build/') debe fallar con error claro
def test_cra_wrong_output_dir_fails_clearly(worker, test_hosting_github):
    test_hosting_github.output_directory = "public"
    # El repo de test tiene package.json con react-scripts y genera build/
    result = worker.run_import_pipeline(test_hosting_github.id)
    assert result.status == "failed"
    assert "output directory" in result.error_message.lower()
    # No debe desplegar un sitio vacío silenciosamente

# Test: smoke test post-deploy verifica que index.html existe
def test_smoke_test_detects_empty_deploy(worker, test_hosting_github):
    # Deploy con directorio vacío
    result = worker.run_import_pipeline(test_hosting_github.id)
    assert result.smoke_test_passed is False
```
