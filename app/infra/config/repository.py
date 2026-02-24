import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from app.infra.config.models import TenantConfigVersion
from app.infra.config.sqlite import get_connection, init_db


class TenantConfigRepository:
    """
    Gestión de reglas/prompts versionados por tenant.
    """

    def __init__(self):
        init_db()

    def create_new_version(
        self,
        tenant_id: str,
        kind: str,
        content: Dict,
    ) -> TenantConfigVersion:
        conn = get_connection()
        cur = conn.cursor()

        # desactivar versión previa activa para este tenant y tipo
        cur.execute(
            """
            UPDATE tenant_configs
            SET active = 0
            WHERE tenant_id = ? AND kind = ? AND active = 1
            """,
            (tenant_id, kind),
        )

        # obtener siguiente versión incremental
        cur.execute(
            """
            SELECT MAX(version) FROM tenant_configs
            WHERE tenant_id = ? AND kind = ?
            """,
            (tenant_id, kind),
        )
        row = cur.fetchone()
        next_version = (row[0] or 0) + 1 if row else 1

        cfg = TenantConfigVersion(
            config_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            version=next_version,
            kind=kind,
            content=content,
            created_at=datetime.now(timezone.utc),
            active=True,
        )

        cur.execute(
            """
            INSERT INTO tenant_configs
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cfg.config_id,
                cfg.tenant_id,
                cfg.version,
                cfg.kind,
                json.dumps(cfg.content),
                cfg.created_at.isoformat(),
                1,
            ),
        )

        conn.commit()
        conn.close()
        return cfg

    def get_active(self, tenant_id: str, kind: str) -> Dict:
        """
        Retorna el contenido de la configuración activa.
        """
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT content FROM tenant_configs
            WHERE tenant_id = ? AND kind = ? AND active = 1
            """,
            (tenant_id, kind),
        )

        row = cur.fetchone()
        conn.close()

        return json.loads(row["content"]) if row else {}

    def get_all_versions(self, tenant_id: str, kind: str) -> list[TenantConfigVersion]:
        """
        Retorna historial de versiones para un tenant y tipo.
        """
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT * FROM tenant_configs
            WHERE tenant_id = ? AND kind = ?
            ORDER BY version DESC
            """,
            (tenant_id, kind),
        )

        rows = cur.fetchall()
        conn.close()

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
