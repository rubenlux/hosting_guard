---
incident_id: COMPOUND_TLD_APEX_MISCLASSIFICATION
incident_type: domain_processing_error
severity: medium
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions: []
forbidden_actions:
  - auto_generate_ssl_with_wrong_apex
  - modify_dns_records_automatically
signatures:
  - "compound TLD"
  - "apex misclassification"
  - "tldextract"
  - ".com.ar"
  - ".co.uk"
---

# COMPOUND_TLD_APEX_MISCLASSIFICATION

## Síntoma
Un cliente configura un dominio personalizado con TLD compuesto (ej: `miempresa.com.ar`, `mysite.co.uk`, `shop.com.mx`). La plataforma extrae el apex incorrecto, lo que causa:
- Generación de certificado SSL con el dominio incorrecto (ej: solicita cert para `ar` en lugar de `miempresa.com.ar`).
- Verificación DNS que falla porque se verifica el registro incorrecto.
- El dominio personalizado queda en estado de error o pendiente indefinidamente.

## Impacto
- El dominio personalizado del cliente no puede activarse correctamente.
- Sin SSL válido, los navegadores muestran advertencia de seguridad.
- La verificación de propiedad del dominio falla, bloqueando la activación.
- No afecta a otros hostings ni a dominios con TLD simple (`.com`, `.net`, `.org`).
- El cliente reporta "mi dominio no funciona" o "error SSL".

## Evidencia
```python
# Extracción incorrecta (lógica naive):
domain = "miempresa.com.ar"
parts = domain.split(".")
apex = ".".join(parts[-2:])  # → "com.ar"  ← INCORRECTO (es el TLD, no el apex)

# Extracción correcta:
# apex debería ser "miempresa.com.ar" (o simplemente "miempresa" es el SLD)
# TLD compuesto: "com.ar"
# Apex (registered domain): "miempresa.com.ar"
```

```
ERROR: SSL certificate request failed for domain 'ar'
# o:
ERROR: DNS verification failed: expected TXT record on '_acme-challenge.com.ar'
# en lugar de '_acme-challenge.miempresa.com.ar'
```

```bash
docker compose logs app | grep -E "com\.ar|co\.uk|apex|tldextract|SSL.*failed"
```

## Causa raíz
La función de extracción del apex del dominio usa una lógica naive que divide por `.` y toma los últimos 2 elementos:
```python
# Código problemático:
def extract_apex(domain: str) -> str:
    parts = domain.split(".")
    return ".".join(parts[-2:])  # Falla con TLDs compuestos
```

Esta lógica es incorrecta para TLDs compuestos:
- `miempresa.com.ar` → partes: `["miempresa", "com", "ar"]` → toma `["com", "ar"]` = `"com.ar"` ❌
- Correcto: apex = `"miempresa.com.ar"`, TLD = `"com.ar"`, SLD = `"miempresa"` ✓

TLDs compuestos comunes afectados: `.com.ar`, `.com.br`, `.co.uk`, `.co.nz`, `.com.mx`, `.com.co`, `.org.ar`, `.net.ar`, `.com.pe`, `.com.ve`.

## Diagnósticos equivocados
- **"El dominio no está registrado"**: El dominio existe; el problema es en la extracción del apex en HostingGuard.
- **"El cliente configuró mal el DNS"**: La verificación DNS falla porque HostingGuard verifica el registro incorrecto, no porque el cliente haya configurado mal el DNS.
- **"Let's Encrypt rechazó el dominio"**: Let's Encrypt rechaza porque se le pide un cert para un TLD o dominio incorrecto, no por límites de rate.
- **"El dominio no soporta SSL"**: Todos los dominios con TLD compuesto válido soportan SSL; el problema es de extracción del apex.

## Diagnóstico rápido
```bash
# 1. Verificar qué apex extrae la plataforma para el dominio del cliente
docker compose exec app python -c "
from app.services.domain_service import extract_apex
domain = 'miempresa.com.ar'
print(f'Apex extraído: {extract_apex(domain)}')
print(f'Esperado: miempresa.com.ar')
"

# 2. Verificar si tldextract está instalado
docker compose exec app python -c "import tldextract; print(tldextract.__version__)"

# 3. Probar con tldextract directamente
docker compose exec app python -c "
import tldextract
result = tldextract.extract('miempresa.com.ar')
print(f'subdomain={result.subdomain}, domain={result.domain}, suffix={result.suffix}')
print(f'registered_domain={result.registered_domain}')
# registered_domain = 'miempresa.com.ar' ← este es el apex correcto
"

# 4. Listar dominios personalizados afectados en BD
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"\"\"
  SELECT id, custom_domain, ssl_status
  FROM hostings
  WHERE custom_domain LIKE '%.com.ar'
     OR custom_domain LIKE '%.co.uk'
     OR custom_domain LIKE '%.com.br'
     OR custom_domain LIKE '%.com.mx'
\"\"\"))
for row in result: print(row)
"
```

## Solución manual
### Fix del código usando tldextract:
```python
# Instalar si no está en requirements.txt:
# pip install tldextract

import tldextract

def extract_apex(domain: str) -> str:
    """
    Extrae el dominio registrado (apex) correctamente, incluyendo TLDs compuestos.
    
    Ejemplos:
    - 'miempresa.com.ar' → 'miempresa.com.ar'
    - 'www.mysite.co.uk' → 'mysite.co.uk'
    - 'blog.example.com' → 'example.com'
    """
    extracted = tldextract.extract(domain)
    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}"
    # Fallback: si tldextract no puede parsear, usar lógica original con warning
    logger.warning(f"tldextract could not parse domain: {domain}, falling back to naive extraction")
    parts = domain.split(".")
    return ".".join(parts[-2:])

def extract_subdomain(domain: str) -> str:
    """Retorna el subdominio si existe, o string vacío."""
    extracted = tldextract.extract(domain)
    return extracted.subdomain
```

### Re-procesar dominios afectados:
```bash
# Tras el fix de código y redeploy:
# Re-intentar la verificación DNS y generación SSL para dominios afectados
docker compose exec app python -c "
from app.services.domain_service import retry_domain_verification
# Para cada hosting con dominio compuesto afectado:
retry_domain_verification(hosting_id=X)
"
```

## Fix permanente
1. Reemplazar la extracción naive de apex por `tldextract` en todos los lugares:
   - `app/services/domain_service.py`
   - Cualquier otro módulo que procese dominios personalizados

2. Añadir `tldextract` a `requirements.txt` si no está.

3. Configurar `tldextract` para usar una Public Suffix List cacheada (evitar llamadas HTTP en producción):
   ```python
   # En startup o config:
   tldextract.TLDExtract(cache_dir="/tmp/tldextract_cache")
   ```

4. Añadir tests con dominios de TLD compuesto:
   ```python
   @pytest.mark.parametrize("domain,expected_apex", [
       ("miempresa.com.ar", "miempresa.com.ar"),
       ("www.mysite.co.uk", "mysite.co.uk"),
       ("shop.com.mx", "shop.com.mx"),
       ("blog.example.com", "example.com"),
       ("sub.domain.co.nz", "domain.co.nz"),
   ])
   def test_extract_apex(domain, expected_apex):
       assert extract_apex(domain) == expected_apex
   ```

## Señales para detección automática
- `ssl_status = 'failed'` en hostings con `custom_domain` que contiene TLD compuesto
- Error de cert request con dominio de 2 partes cuando el dominio tiene 3+ partes
- Log pattern: `SSL.*failed.*\.ar\b` o similar para TLDs de 2 letras de país

## Auto-remediation permitido
Ninguna. La corrección requiere fix de código, tests y redeploy. No se debe intentar generar SSL o modificar DNS sin el apex correcto.

## Auto-remediation prohibido
- `auto_generate_ssl_with_wrong_apex`: Solicitar un certificado SSL con el apex incorrecto (e.g., para `com.ar`) fallará, puede consumir límites de rate de Let's Encrypt, y no resuelve el problema.
- `modify_dns_records_automatically`: Nunca modificar registros DNS del cliente de forma automática. El proceso de verificación DNS es iniciado por el cliente; HostingGuard solo verifica.

## Dashboard esperado
- **Domain status**: todos los dominios con TLD compuesto en estado `active` con SSL válido.
- **SSL generation**: tasa de éxito > 99% para todos los tipos de dominio.
- **DNS verification**: verificación exitosa en todos los dominios configurados correctamente.

## RAG usage
Recuperar con: `compound TLD apex extraction com.ar co.uk tldextract`, `custom domain SSL failed compound TLD`, `apex misclassification domain checker`.
Contexto relevante: `app/services/domain_service.py`, función de extracción de apex, pipeline de activación de dominio personalizado.

## Tests/Chaos
```python
# Tests parametrizados de extracción de apex
@pytest.mark.parametrize("domain,expected", [
    ("miempresa.com.ar", "miempresa.com.ar"),
    ("www.mysite.co.uk", "mysite.co.uk"),
    ("tienda.com.mx", "tienda.com.mx"),
    ("blog.example.com", "example.com"),
    ("sub.blog.example.com", "example.com"),
    ("shop.com.br", "shop.com.br"),
])
def test_extract_apex_compound_tld(domain, expected):
    from app.services.domain_service import extract_apex
    assert extract_apex(domain) == expected

# Chaos: intentar activar un dominio .com.ar y verificar que el cert se solicita
# para el apex correcto (miempresa.com.ar), no para 'com.ar' ni 'ar'
```
