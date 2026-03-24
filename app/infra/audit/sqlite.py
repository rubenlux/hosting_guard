import os
import sqlite3
from pathlib import Path

# Carga la ruta desde el entorno (útil para Docker /app/data/)
DB_PATH = Path(os.getenv("AUDIT_DB_PATH", "audit_events.sqlite"))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Tabla de decisiones (AI Advisory)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS decision_events (
            event_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            decision_id TEXT NOT NULL,
            overall_status TEXT NOT NULL,
            confidence_level TEXT NOT NULL,
            requires_human_attention INTEGER NOT NULL,
            payload_min TEXT NOT NULL,
            version INTEGER NOT NULL
        )
        """
    )

    # Tabla de acciones humanas (Approve/Reject)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS human_action_events (
            action_event_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            decision_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason TEXT,
            version INTEGER NOT NULL
        )
        """
    )

    # Tabla de ejecución (Dry-run / Execute / Rollback)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_events (
            execution_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            decision_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            status TEXT NOT NULL,
            version INTEGER NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()
