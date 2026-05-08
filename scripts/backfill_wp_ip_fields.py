"""
One-time backfill: populate client_ip, ip_source, ip_confidence
for legacy wp_* activity_events that have source_ip but not the
newer IP classification fields added in the 2026-05-08 refactor.

Safe to run multiple times (WHERE clause limits to rows that still
need the update). Adds legacy_ip_backfill=true to metadata so rows
updated here are distinguishable from rows produced by new code.

Usage:
    python scripts/backfill_wp_ip_fields.py [--dry-run]
"""
import argparse
import sys

_CF_PREFIXES = (
    "103.21.", "103.22.", "103.31.",
    "104.16.", "104.17.", "104.18.", "104.19.",
    "104.20.", "104.21.", "104.22.", "104.23.",
    "108.162.", "141.101.",
    "162.158.", "162.159.",
    "172.64.", "172.65.", "172.66.", "172.67.",
    "172.68.", "172.69.", "172.70.", "172.71.",
    "173.245.", "188.114.", "190.93.", "197.234.", "198.41.",
)

_COUNT_SQL = """
SELECT COUNT(*) AS cnt
FROM activity_events
WHERE event_type ILIKE 'wp_%'
  AND metadata ? 'source_ip'
  AND NULLIF(metadata->>'source_ip', '') IS NOT NULL
  AND (
    NOT (metadata ? 'client_ip')
    OR NULLIF(metadata->>'client_ip', '') IS NULL
    OR NOT (metadata ? 'ip_confidence')
    OR NULLIF(metadata->>'ip_confidence', '') IS NULL
  )
"""

_UPDATE_SQL = """
UPDATE activity_events
SET metadata =
  jsonb_set(
    jsonb_set(
      jsonb_set(
        jsonb_set(
          metadata,
          '{client_ip}',
          to_jsonb(COALESCE(NULLIF(metadata->>'client_ip', ''), metadata->>'source_ip')),
          true
        ),
        '{ip_source}',
        to_jsonb(COALESCE(NULLIF(metadata->>'ip_source', ''), 'remote_addr')),
        true
      ),
      '{ip_confidence}',
      to_jsonb(
        CASE
          WHEN (metadata->>'source_ip') LIKE '103.21.%%'
            OR (metadata->>'source_ip') LIKE '103.22.%%'
            OR (metadata->>'source_ip') LIKE '103.31.%%'
            OR (metadata->>'source_ip') LIKE '104.16.%%'
            OR (metadata->>'source_ip') LIKE '104.17.%%'
            OR (metadata->>'source_ip') LIKE '104.18.%%'
            OR (metadata->>'source_ip') LIKE '104.19.%%'
            OR (metadata->>'source_ip') LIKE '104.20.%%'
            OR (metadata->>'source_ip') LIKE '104.21.%%'
            OR (metadata->>'source_ip') LIKE '104.22.%%'
            OR (metadata->>'source_ip') LIKE '104.23.%%'
            OR (metadata->>'source_ip') LIKE '108.162.%%'
            OR (metadata->>'source_ip') LIKE '141.101.%%'
            OR (metadata->>'source_ip') LIKE '162.158.%%'
            OR (metadata->>'source_ip') LIKE '162.159.%%'
            OR (metadata->>'source_ip') LIKE '172.64.%%'
            OR (metadata->>'source_ip') LIKE '172.65.%%'
            OR (metadata->>'source_ip') LIKE '172.66.%%'
            OR (metadata->>'source_ip') LIKE '172.67.%%'
            OR (metadata->>'source_ip') LIKE '172.68.%%'
            OR (metadata->>'source_ip') LIKE '172.69.%%'
            OR (metadata->>'source_ip') LIKE '172.70.%%'
            OR (metadata->>'source_ip') LIKE '172.71.%%'
            OR (metadata->>'source_ip') LIKE '173.245.%%'
            OR (metadata->>'source_ip') LIKE '188.114.%%'
            OR (metadata->>'source_ip') LIKE '190.93.%%'
            OR (metadata->>'source_ip') LIKE '197.234.%%'
            OR (metadata->>'source_ip') LIKE '198.41.%%'
          THEN 'proxy_observed'
          ELSE 'direct'
        END
      ),
      true
    ),
    '{legacy_ip_backfill}',
    'true'::jsonb,
    true
  )
WHERE event_type ILIKE 'wp_%'
  AND metadata ? 'source_ip'
  AND NULLIF(metadata->>'source_ip', '') IS NOT NULL
  AND (
    NOT (metadata ? 'client_ip')
    OR NULLIF(metadata->>'client_ip', '') IS NULL
    OR NOT (metadata ? 'ip_confidence')
    OR NULLIF(metadata->>'ip_confidence', '') IS NULL
  )
"""


def run(dry_run: bool) -> None:
    from app.infra.db import get_connection, release_connection

    conn = get_connection()
    try:
        cur = conn.cursor()

        # Count
        cur.execute(_COUNT_SQL)
        row = cur.fetchone()
        count = row["cnt"] if row else 0
        print(f"Legacy events needing backfill: {count}")

        if count == 0:
            print("Nothing to do.")
            return

        if dry_run:
            print("[dry-run] Would update {} rows — no changes made.".format(count))
            return

        # Update
        cur.execute(_UPDATE_SQL)
        updated = cur.rowcount
        conn.commit()
        print(f"Updated {updated} rows.")

        # Verify
        cur.execute(_COUNT_SQL)
        row = cur.fetchone()
        remaining = row["cnt"] if row else 0
        if remaining == 0:
            print("Verification OK: legacy_ip_missing = 0")
        else:
            print(f"WARNING: {remaining} rows still missing client_ip/ip_confidence after update")
            sys.exit(1)

    except Exception as exc:
        print(f"ERROR: {exc}")
        try:
            conn.rollback()
        except Exception:
            pass
        sys.exit(1)
    finally:
        release_connection(conn)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill IP fields for legacy wp_* activity_events")
    parser.add_argument("--dry-run", action="store_true", help="Count without modifying")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
