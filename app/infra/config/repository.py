import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional
from app.infra.config.models import TenantConfigVersion
from app.infra.db import get_connection
from app.infra.migrations import init_db

class TenantConfigRepository:
    """Gestión de reglas/prompts versionados por tenant en PostgreSQL."""
    def __init__(self):
        init_db()

    def create_new_version(self, tenant_id: str, kind: str, content: Dict) -> TenantConfigVersion:
        conn = get_connection()
        cur = conn.cursor()
        # 1. Desactivar versión previa
        cur.execute(
            "UPDATE tenant_configs SET active = 0 WHERE tenant_id = %s AND kind = %s AND active = 1",
            (tenant_id, kind),
        )
        # 2. Obtener siguiente versión
        cur.execute(
            "SELECT MAX(version) AS max_version FROM tenant_configs WHERE tenant_id = %s AND kind = %s",
            (tenant_id, kind),
        )
        row = cur.fetchone()
        next_version = (row["max_version"] or 0) + 1 if row else 1

        cfg = TenantConfigVersion(
            config_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            version=next_version,
            kind=kind,
            content=content,
            created_at=datetime.now(timezone.utc),
            active=True,
        )

        # 3. Insertar nueva versión
        cur.execute(
            "INSERT INTO tenant_configs (config_id, tenant_id, version, kind, content, created_at, active) "
            "VALUES (%s, %s, %s, %s, %s, %s, 1)",
            (cfg.config_id, cfg.tenant_id, cfg.version, cfg.kind, json.dumps(cfg.content), cfg.created_at.isoformat()),
        )
        conn.commit()
        return cfg

    def get_active(self, tenant_id: str, kind: str) -> Dict:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT content FROM tenant_configs WHERE tenant_id = %s AND kind = %s AND active = 1",
            (tenant_id, kind),
        )
        row = cur.fetchone()
        return json.loads(row["content"]) if row else {}

    def get_all_versions(self, tenant_id: str, kind: str) -> list[TenantConfigVersion]:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM tenant_configs WHERE tenant_id = %s AND kind = %s ORDER BY version DESC",
            (tenant_id, kind),
        )
        rows = cur.fetchall()
        return [
            TenantConfigVersion(
                config_id=r["config_id"],
                tenant_id=r["tenant_id"],
                version=r["version"],
                kind=r["kind"],
                content=json.loads(r["content"]),
                created_at=datetime.fromisoformat(r["created_at"]),
                active=bool(r["active"]),
            )
            for r in rows
        ]
