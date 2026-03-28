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

    # Tabla de usuarios
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            balance REAL DEFAULT 0.0,
            has_payment_method INTEGER DEFAULT 0,
            autoscale_enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )

    # Migración (añadir columnas si no existen)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN has_payment_method INTEGER DEFAULT 0")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN autoscale_enabled INTEGER DEFAULT 1")
    except:
        pass

    # Tabla de hostings (proyectos)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS hostings (
            hosting_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            subdomain TEXT NOT NULL,
            container_name TEXT NOT NULL,
            plan TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        """
    )

    # Tabla de eventos del orquestador (Smart Monitoring)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orchestrator_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            container_name TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        """
    )

    conn.commit()
    conn.close()
