import sqlite3
import os
from pathlib import Path

# Carga la ruta desde el entorno (útil para Docker /app/data/)
DB_PATH = Path(os.getenv("CONFIG_DB_PATH", "tenant_configs.sqlite"))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_configs (
            config_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            active INTEGER NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()
