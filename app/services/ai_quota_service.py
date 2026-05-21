"""AI usage quota enforcement.

Free plan:  max 10 all-time queries (support_chat feature) + max 3/day.
Paid plans: monthly limit from plan_economics.included_ai_queries_month.
            0 = unlimited (used for plans not yet in plan_economics).

Usage:
    check_ai_quota(user_id, feature, plan)   # raises HTTP 429 if exceeded
    record_ai_usage(user_id, feature, plan)  # call AFTER successful AI response
    get_ai_usage(user_id, ...)               # summary for admin/dashboard
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)

_FREE_TRIAL_TOTAL = 10
_FREE_DAILY_LIMIT = 3


def _count_usage(user_id: int, feature: str, since: datetime) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT COALESCE(SUM(units), 0) AS total
               FROM ai_usage_events
               WHERE user_id = %s AND feature = %s AND created_at >= %s""",
            (user_id, feature, since),
        )
        row = cur.fetchone()
        return int(row["total"]) if row else 0
    finally:
        release_connection(conn)


def _get_monthly_limit(plan: str) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT included_ai_queries_month FROM plan_economics WHERE plan_name = %s",
            (plan,),
        )
        row = cur.fetchone()
        return int(row["included_ai_queries_month"]) if row else 0
    finally:
        release_connection(conn)


def check_ai_quota(user_id: int, feature: str, plan: str) -> None:
    """Raise HTTP 429 if the user has exceeded their AI quota for this feature."""
    now = datetime.now(timezone.utc)

    if plan == "free":
        epoch = datetime(2020, 1, 1, tzinfo=timezone.utc)
        total_used = _count_usage(user_id, feature, since=epoch)
        if total_used >= _FREE_TRIAL_TOTAL:
            raise HTTPException(
                status_code=429,
                detail={
                    "detail": "Has alcanzado el límite de consultas IA del plan gratuito.",
                    "code": "ai_quota_exceeded",
                    "limit": _FREE_TRIAL_TOTAL,
                    "used": total_used,
                    "reset_at": None,
                },
            )
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_used = _count_usage(user_id, feature, since=day_start)
        if daily_used >= _FREE_DAILY_LIMIT:
            next_day = (day_start + timedelta(days=1)).isoformat()
            raise HTTPException(
                status_code=429,
                detail={
                    "detail": "Has alcanzado el límite diario de consultas IA.",
                    "code": "ai_quota_exceeded",
                    "limit": _FREE_DAILY_LIMIT,
                    "used": daily_used,
                    "reset_at": next_day,
                },
            )
    else:
        monthly_limit = _get_monthly_limit(plan)
        if monthly_limit <= 0:
            return
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_used = _count_usage(user_id, feature, since=month_start)
        if monthly_used >= monthly_limit:
            if now.month == 12:
                next_month = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                next_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            raise HTTPException(
                status_code=429,
                detail={
                    "detail": "Has alcanzado el límite mensual de consultas IA de tu plan.",
                    "code": "ai_quota_exceeded",
                    "limit": monthly_limit,
                    "used": monthly_used,
                    "reset_at": next_month.isoformat(),
                },
            )


def record_ai_usage(
    user_id: int,
    feature: str,
    plan: str,
    units: int = 1,
    metadata: Optional[dict] = None,
) -> None:
    """Insert one row into ai_usage_events. Call only after a successful AI response."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO ai_usage_events (user_id, plan, feature, units, metadata, created_at)
               VALUES (%s, %s, %s, %s, %s, NOW())""",
            (user_id, plan, feature, units, metadata or {}),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to record AI usage for user_id=%s feature=%s", user_id, feature)
    finally:
        release_connection(conn)


def get_ai_usage_summary(
    user_id: Optional[int] = None,
    feature: Optional[str] = None,
    plan: Optional[str] = None,
    days: int = 30,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return aggregated usage for admin view. All filters are optional."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        since = datetime.now(timezone.utc) - timedelta(days=days)

        where = ["created_at >= %s"]
        params: list = [since]

        if user_id is not None:
            where.append("user_id = %s")
            params.append(user_id)
        if feature:
            where.append("feature = %s")
            params.append(feature)
        if plan:
            where.append("plan = %s")
            params.append(plan)

        where_sql = " AND ".join(where)

        cur.execute(
            f"""SELECT user_id, plan, feature,
                       SUM(units) AS total_units,
                       COUNT(*) AS calls,
                       MAX(created_at) AS last_call
                FROM ai_usage_events
                WHERE {where_sql}
                GROUP BY user_id, plan, feature
                ORDER BY total_units DESC
                LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        rows = [dict(r) for r in cur.fetchall()]

        # Total distinct users affected
        cur.execute(
            f"SELECT COUNT(DISTINCT user_id) AS cnt FROM ai_usage_events WHERE {where_sql}",
            params,
        )
        total_users = (cur.fetchone() or {}).get("cnt", 0)

        return {"rows": rows, "total_users": total_users, "days": days}
    finally:
        release_connection(conn)


def get_user_ai_quota_status(user_id: int, feature: str, plan: str) -> dict:
    """Return current usage and limits for a single user — used by the user-facing dashboard."""
    now = datetime.now(timezone.utc)

    if plan == "free":
        epoch = datetime(2020, 1, 1, tzinfo=timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        total_used = _count_usage(user_id, feature, since=epoch)
        daily_used = _count_usage(user_id, feature, since=day_start)
        next_day = (day_start + timedelta(days=1)).isoformat()
        return {
            "plan": plan,
            "feature": feature,
            "trial_total": {"used": total_used, "limit": _FREE_TRIAL_TOTAL},
            "daily": {"used": daily_used, "limit": _FREE_DAILY_LIMIT, "resets_at": next_day},
        }
    else:
        monthly_limit = _get_monthly_limit(plan)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_used = _count_usage(user_id, feature, since=month_start)
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return {
            "plan": plan,
            "feature": feature,
            "monthly": {
                "used": monthly_used,
                "limit": monthly_limit,
                "resets_at": next_month.isoformat(),
            },
        }
