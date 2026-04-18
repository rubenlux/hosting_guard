from datetime import datetime, timezone
from typing import Optional, Dict, List
from app.infra.db import get_connection, release_connection


class ImportRepository:

    def create_job(self, hosting_id: int, user_id: int) -> int:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO import_jobs (hosting_id, user_id, status, logs, created_at, updated_at)
                VALUES (%s, %s, 'uploading', '', %s, %s)
                RETURNING job_id
                """,
                (hosting_id, user_id,
                 datetime.now(timezone.utc).isoformat(),
                 datetime.now(timezone.utc).isoformat()),
            )
            row = cursor.fetchone()
            conn._conn.commit()
            return row["job_id"]
        finally:
            release_connection(conn)

    def set_status(self, job_id: int, status: str, error: str = None):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE import_jobs
                SET status = %s, error = %s, updated_at = %s
                WHERE job_id = %s
                """,
                (status, error, datetime.now(timezone.utc).isoformat(), job_id),
            )
            conn._conn.commit()
        finally:
            release_connection(conn)

    def append_log(self, job_id: int, line: str):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE import_jobs
                SET logs = logs || %s, updated_at = %s
                WHERE job_id = %s
                """,
                (line + "\n", datetime.now(timezone.utc).isoformat(), job_id),
            )
            conn._conn.commit()
        finally:
            release_connection(conn)

    def set_domains(self, job_id: int, original_domain: str, new_domain: str):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE import_jobs
                SET original_domain = %s, new_domain = %s, updated_at = %s
                WHERE job_id = %s
                """,
                (original_domain, new_domain, datetime.now(timezone.utc).isoformat(), job_id),
            )
            conn._conn.commit()
        finally:
            release_connection(conn)

    def get_job(self, job_id: int, user_id: Optional[int] = None) -> Optional[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if user_id is not None:
                cursor.execute(
                    "SELECT * FROM import_jobs WHERE job_id = %s AND user_id = %s",
                    (job_id, user_id),
                )
            else:
                cursor.execute("SELECT * FROM import_jobs WHERE job_id = %s", (job_id,))
            return cursor.fetchone()
        finally:
            release_connection(conn)

    def list_jobs(self, user_id: int, hosting_id: Optional[int] = None) -> List[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if hosting_id:
                cursor.execute(
                    "SELECT * FROM import_jobs WHERE user_id = %s AND hosting_id = %s ORDER BY created_at DESC LIMIT 10",
                    (user_id, hosting_id),
                )
            else:
                cursor.execute(
                    "SELECT * FROM import_jobs WHERE user_id = %s ORDER BY created_at DESC LIMIT 20",
                    (user_id,),
                )
            return cursor.fetchall() or []
        finally:
            release_connection(conn)
