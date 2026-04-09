import time
import logging
from datetime import datetime, timezone, timedelta
from app.infra.db import get_connection, release_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill")

def run_backfill():
    # 1. Obtener punto de inicio (min created_at en legacy)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(created_at) FROM pixel_events_legacy")
        row = cursor.fetchone()
        last_ts = row[0] if row and row[0] else None
        
        if not last_ts:
            logger.info("No legacy data found to migrate.")
            return

        logger.info(f"Starting backfill from: {last_ts}")
    finally:
        release_connection(conn)

    total_migrated = 0
    batch_size = 5000

    while True:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            
            # 2. Migración por Rango (Cursor-based) para eficiencia extrema
            # ON CONFLICT DO NOTHING evita duplicar lo que el Dual Write ya insertó
            cursor.execute("""
                INSERT INTO pixel_events
                SELECT *
                FROM pixel_events_legacy
                WHERE created_at >= %s
                  AND created_at < now() - interval '2 minutes'
                ORDER BY created_at
                LIMIT %s
                ON CONFLICT DO NOTHING
                RETURNING created_at
            """, (last_ts, batch_size))

            rows = cursor.fetchall()
            
            if not rows:
                logger.info("Backfill completed successfully.")
                break

            # Actualizar cursor al último timestamp procesado
            last_ts = rows[-1][0]
            migrated_in_batch = len(rows)
            total_migrated += migrated_in_batch
            
            conn.commit()
            logger.info(f"Batch migrated: {migrated_in_batch} records. Last TS: {last_ts}. Total: {total_migrated}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Error during backfill batch: {e}", exc_info=True)
            break
        finally:
            release_connection(conn)

        # 3. Delay controlado para proteger IOPS de producción
        time.sleep(0.2)

if __name__ == "__main__":
    run_backfill()
