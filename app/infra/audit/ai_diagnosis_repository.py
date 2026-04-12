"""
AIDiagnosisRepository — append-only store for structured AI diagnoses.

Schema: ai_diagnosis table (see migrations.py).
All fields derived from the LLM JSON response.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)


class AIDiagnosisRepository:

    def save(
        self,
        hosting_id: int,
        user_id: Optional[int],
        parsed: Dict,
        raw_response: str,
    ) -> Optional[Dict]:
        """
        Persist a structured diagnosis. Returns the saved row dict, or None on error.
        """
        location = parsed.get("location") or {}
        fix      = parsed.get("fix") or {}

        conn = get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                """
                INSERT INTO ai_diagnosis
                    (hosting_id, user_id, severity, summary, root_cause,
                     file_path, line_number, service,
                     evidence, impact,
                     fix_action, fix_steps,
                     confidence, raw_response, created_at)
                VALUES
                    (%s, %s, %s, %s, %s,
                     %s, %s, %s,
                     %s, %s,
                     %s, %s,
                     %s, %s, %s)
                RETURNING id
                """,
                (
                    hosting_id,
                    user_id,
                    parsed.get("severity"),
                    parsed.get("summary"),
                    parsed.get("root_cause"),
                    location.get("file"),
                    str(location.get("line")) if location.get("line") else None,
                    location.get("service"),
                    json.dumps(parsed.get("evidence") or []),
                    parsed.get("impact"),
                    fix.get("action"),
                    json.dumps(fix.get("steps") or []),
                    parsed.get("confidence"),
                    raw_response,
                    now,
                ),
            )
            conn.commit()
            row_id = cursor.fetchone()
            return {**parsed, "id": row_id["id"] if row_id else None, "created_at": now}
        except Exception:
            logger.exception("Failed to save AI diagnosis for hosting_id=%s", hosting_id)
            conn.rollback()
            return None
        finally:
            release_connection(conn)

    def get_by_hosting(self, hosting_id: int, limit: int = 10) -> List[Dict]:
        """
        Return the most recent diagnoses for a hosting, newest first.
        JSON fields are deserialized back to Python lists.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, severity, summary, root_cause,
                       file_path, line_number, service,
                       evidence, impact,
                       fix_action, fix_steps,
                       confidence, created_at
                FROM   ai_diagnosis
                WHERE  hosting_id = %s
                ORDER  BY created_at DESC
                LIMIT  %s
                """,
                (hosting_id, limit),
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["evidence"]  = _parse_json(d.get("evidence"),  [])
                d["fix_steps"] = _parse_json(d.get("fix_steps"), [])
                result.append(d)
            return result
        except Exception:
            logger.exception("Failed to fetch AI diagnoses for hosting_id=%s", hosting_id)
            return []
        finally:
            release_connection(conn)


def _parse_json(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value  # already deserialized by psycopg2 JSONB adapter
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default
