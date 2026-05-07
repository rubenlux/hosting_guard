import secrets
import logging
from datetime import datetime, timezone
from typing import Optional
from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)


class DomainRepository:
    def add_domain(self, user_id: int, hosting_id: int, domain: str, domain_type: str) -> int:
        token = secrets.token_hex(16)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO custom_domains
                   (user_id, hosting_id, domain, domain_type, verification_token)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING domain_id""",
                (user_id, hosting_id, domain.lower().strip(), domain_type, token),
            )
            row = cur.fetchone()
            conn.commit()
            return row["domain_id"]
        finally:
            release_connection(conn)

    def get_domains(self, hosting_id: int, user_id: int) -> list:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT * FROM custom_domains
                   WHERE hosting_id = %s AND user_id = %s
                   ORDER BY created_at""",
                (hosting_id, user_id),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            release_connection(conn)

    def get_domain(self, domain_id: int, user_id: int) -> Optional[dict]:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM custom_domains WHERE domain_id = %s AND user_id = %s",
                (domain_id, user_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def get_by_domain_name(self, domain: str) -> Optional[dict]:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM custom_domains WHERE domain = %s", (domain.lower(),))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def update_status(self, domain_id: int, *,
                      dns_status: Optional[str] = None,
                      ssl_status: Optional[str] = None,
                      error_message: Optional[str] = None,
                      verified: bool = False) -> None:
        conn = get_connection()
        try:
            cur = conn.cursor()
            sets = ["last_checked_at = NOW()"]
            vals: list = []
            if dns_status is not None:
                sets.append("dns_status = %s")
                vals.append(dns_status)
            if ssl_status is not None:
                sets.append("ssl_status = %s")
                vals.append(ssl_status)
            if error_message is not None:
                sets.append("error_message = %s")
                vals.append(error_message)
            if verified:
                sets.append("verified_at = NOW()")
            vals.append(domain_id)
            cur.execute(f"UPDATE custom_domains SET {', '.join(sets)} WHERE domain_id = %s", vals)
            conn.commit()
        finally:
            release_connection(conn)

    def set_primary(self, domain_id: int, hosting_id: int) -> None:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE custom_domains SET is_primary = 0 WHERE hosting_id = %s",
                (hosting_id,),
            )
            cur.execute(
                "UPDATE custom_domains SET is_primary = 1 WHERE domain_id = %s",
                (domain_id,),
            )
            conn.commit()
        finally:
            release_connection(conn)

    def delete_domain(self, domain_id: int, user_id: int) -> bool:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM custom_domains WHERE domain_id = %s AND user_id = %s",
                (domain_id, user_id),
            )
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            release_connection(conn)

    def get_pending_domains(self) -> list:
        """Return domains in pending/failed state not checked in the last 5 minutes."""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT d.*, h.container_name, h.subdomain
                   FROM custom_domains d
                   JOIN hostings h ON h.hosting_id = d.hosting_id
                   WHERE d.dns_status IN ('pending', 'failed')
                     AND (d.last_checked_at IS NULL
                          OR d.last_checked_at < NOW() - INTERVAL '5 minutes')
                   ORDER BY d.created_at
                   LIMIT 50""",
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            release_connection(conn)
