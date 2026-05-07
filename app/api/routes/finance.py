import math
from fastapi import APIRouter, Depends
from app.api.security import require_role

router = APIRouter(prefix="/admin/finance", tags=["finance"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_plan_economics(cur) -> dict:
    cur.execute("SELECT * FROM plan_economics")
    return {r["plan_name"]: dict(r) for r in cur.fetchall()}


def _get_cost_settings(cur) -> dict:
    cur.execute("SELECT * FROM cost_settings WHERE id = 1")
    row = cur.fetchone()
    if row:
        return dict(row)
    return {
        "monthly_server_cost_usd": 18.98,
        "cpu_cost_weight": 0.40,
        "ram_cost_weight": 0.40,
        "disk_cost_weight": 0.15,
        "overhead_cost_weight": 0.05,
        "backup_cost_per_gb_month_usd": 0.10,
        "ai_cost_per_query_usd": 0.02,
        "human_support_hourly_cost_usd": 10.0,
        "payment_fee_percent": 6.5,
        "payment_fee_fixed_usd": 0.50,
    }


def _calc_revenue(plan: str, billing_interval: str, plan_ec: dict, cs: dict) -> dict:
    pe = plan_ec.get(plan) or plan_ec.get("free") or {}
    fee_pct = (cs.get("payment_fee_percent") or 6.5) / 100
    fee_fixed = cs.get("payment_fee_fixed_usd") or 0.50

    if billing_interval == "yearly":
        annual = pe.get("annual_price_usd") or 0
        gross_monthly = annual / 12
        fee_monthly = (annual * fee_pct + fee_fixed) / 12 if annual > 0 else 0
    else:
        gross_monthly = pe.get("monthly_price_usd") or 0
        fee_monthly = (gross_monthly * fee_pct + fee_fixed) if gross_monthly > 0 else 0

    net_monthly = gross_monthly - fee_monthly
    return {
        "gross_monthly_revenue": round(gross_monthly, 2),
        "payment_fee_monthly": round(fee_monthly, 2),
        "net_monthly_revenue": round(net_monthly, 2),
    }


def _calc_infra_cost(client: dict, cs: dict,
                     total_cpu: float, total_ram: float, total_disk: float,
                     n_clients: int) -> dict:
    server = cs.get("monthly_server_cost_usd") or 18.98
    cpu_w  = cs.get("cpu_cost_weight") or 0.40
    ram_w  = cs.get("ram_cost_weight") or 0.40
    disk_w = cs.get("disk_cost_weight") or 0.15
    oh_w   = cs.get("overhead_cost_weight") or 0.05
    n      = max(1, n_clients)

    opex = server * (1 - oh_w)

    cpu_frac  = (float(client.get("avg_cpu_pct") or 0)) / max(total_cpu, 1)
    ram_frac  = (float(client.get("total_ram_mb") or 0)) / max(total_ram, 1)
    disk_frac = (float(client.get("total_disk_mb") or 0)) / max(total_disk, 1)

    cpu_cost  = round(cpu_w  * opex * cpu_frac,  4)
    ram_cost  = round(ram_w  * opex * ram_frac,  4)
    disk_cost = round(disk_w * opex * disk_frac, 4)
    overhead  = round(oh_w * server / n, 4)

    backup_gb   = (float(client.get("total_backup_mb") or 0)) / 1024
    backup_cost = round(backup_gb * (cs.get("backup_cost_per_gb_month_usd") or 0.10), 4)

    return {
        "cpu_cost_usd":     cpu_cost,
        "ram_cost_usd":     ram_cost,
        "disk_cost_usd":    disk_cost,
        "overhead_cost_usd": overhead,
        "backup_cost_usd":  backup_cost,
        "ai_cost_usd":      0.0,
        "support_cost_usd": 0.0,
    }


def _recommendation(client: dict, plan_ec: dict, margin_pct: float) -> tuple:
    plan = client.get("plan") or "free"
    pe   = plan_ec.get(plan) or {}

    sites    = int(client.get("hosting_count") or 0)
    bk_gb    = (float(client.get("total_backup_mb") or 0)) / 1024
    disk_gb  = (float(client.get("total_disk_mb") or 0)) / 1024
    cpu      = float(client.get("avg_cpu_pct") or 0)

    inc_sites = pe.get("included_sites") or 999
    inc_bk    = pe.get("included_backup_gb") or 999
    inc_disk  = pe.get("included_disk_gb") or 999

    reasons = []
    if sites > inc_sites:
        reasons.append(f"{sites} sites > {inc_sites} included")
    if inc_bk < 999 and bk_gb > inc_bk:
        reasons.append(f"{bk_gb:.1f}GB backup > {inc_bk}GB included")
    if inc_disk < 999 and disk_gb > inc_disk:
        reasons.append(f"{disk_gb:.1f}GB disk > {inc_disk}GB included")

    if reasons:
        return "upgrade_recommended", "; ".join(reasons)
    if cpu > 85 and plan == "free":
        return "possible_abuse", f"CPU {cpu:.0f}% on free plan"
    if margin_pct < 0:
        return "unprofitable", f"margin {margin_pct:.0f}%"
    if margin_pct < 20:
        return "risk", f"low margin {margin_pct:.0f}%"
    if margin_pct < 40:
        return "review", f"margin {margin_pct:.0f}%"
    return "profitable", f"margin {margin_pct:.0f}%"


def _status_from_margin(margin_pct: float) -> str:
    if margin_pct >= 40:  return "profitable"
    if margin_pct >= 20:  return "review"
    if margin_pct >= 0:   return "risk"
    return "unprofitable"


def _build_tenant_rows(cur, plan_ec: dict, cs: dict) -> list:
    cur.execute(
        """SELECT
             u.user_id, u.email, u.plan,
             COALESCE(u.billing_interval, 'yearly') AS billing_interval,
             u.subscription_status,
             COUNT(DISTINCT h.hosting_id) AS hosting_count,
             ROUND(AVG(lat.cpu_pct)::numeric, 2)   AS avg_cpu_pct,
             ROUND(SUM(lat.mem_mb)::numeric, 0)    AS total_ram_mb,
             ROUND(SUM(lat.disk_mb)::numeric, 0)   AS total_disk_mb,
             COALESCE(SUM(bs.backup_mb), 0)        AS total_backup_mb
           FROM users u
           JOIN hostings h ON h.user_id = u.user_id
                           AND h.status NOT IN ('deleted','expired')
           LEFT JOIN LATERAL (
               SELECT cpu_pct, mem_mb, disk_mb
               FROM hosting_resource_samples
               WHERE hosting_id = h.hosting_id
                 AND sampled_at >= NOW() - INTERVAL '10 minutes'
               ORDER BY sampled_at DESC LIMIT 1
           ) lat ON TRUE
           LEFT JOIN LATERAL (
               SELECT COALESCE(SUM(size_bytes),0)/1048576.0 AS backup_mb
               FROM backups
               WHERE hosting_id = h.hosting_id AND status = 'completed'
           ) bs ON TRUE
           GROUP BY u.user_id, u.email, u.plan, u.billing_interval, u.subscription_status
           ORDER BY u.email"""
    )
    return [dict(r) for r in cur.fetchall()]


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/unit-economics/tenants")
def unit_economics_tenants(_: dict = Depends(require_role("admin"))):
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        plan_ec = _get_plan_economics(cur)
        cs      = _get_cost_settings(cur)
        clients = _build_tenant_rows(cur, plan_ec, cs)
    finally:
        release_connection(conn)

    total_cpu  = sum(float(c.get("avg_cpu_pct") or 0) for c in clients)
    total_ram  = sum(float(c.get("total_ram_mb") or 0) for c in clients)
    total_disk = sum(float(c.get("total_disk_mb") or 0) for c in clients)
    n          = len(clients)

    rows = []
    for c in clients:
        rev  = _calc_revenue(c.get("plan") or "free",
                             c.get("billing_interval") or "yearly",
                             plan_ec, cs)
        cost = _calc_infra_cost(c, cs, total_cpu, total_ram, total_disk, n)

        total_cost  = round(sum(cost.values()), 2)
        net_rev     = rev["net_monthly_revenue"]
        profit      = round(net_rev - total_cost, 2)
        margin_pct  = round((profit / net_rev * 100) if net_rev > 0 else -100.0, 1)

        rec, reason = _recommendation(c, plan_ec, margin_pct)
        status      = rec if rec in ("upgrade_recommended","possible_abuse") else _status_from_margin(margin_pct)

        rows.append({
            "user_id":               c["user_id"],
            "email":                 c["email"],
            "plan":                  c.get("plan") or "free",
            "billing_interval":      c.get("billing_interval") or "yearly",
            "subscription_status":   c.get("subscription_status"),
            "hosting_count":         int(c.get("hosting_count") or 0),
            "avg_cpu_pct":           float(c.get("avg_cpu_pct") or 0),
            "total_ram_mb":          float(c.get("total_ram_mb") or 0),
            "total_disk_mb":         float(c.get("total_disk_mb") or 0),
            "total_backup_mb":       float(c.get("total_backup_mb") or 0),
            **rev,
            **cost,
            "total_cost_usd":        total_cost,
            "profit_usd":            profit,
            "margin_percent":        margin_pct,
            "status":                status,
            "recommendation":        rec,
            "reason":                reason,
        })

    rows.sort(key=lambda x: x["profit_usd"], reverse=True)
    return {"items": rows, "count": len(rows)}


@router.get("/unit-economics/overview")
def unit_economics_overview(_: dict = Depends(require_role("admin"))):
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        plan_ec = _get_plan_economics(cur)
        cs      = _get_cost_settings(cur)
        clients = _build_tenant_rows(cur, plan_ec, cs)
    finally:
        release_connection(conn)

    total_cpu  = sum(float(c.get("avg_cpu_pct") or 0) for c in clients)
    total_ram  = sum(float(c.get("total_ram_mb") or 0) for c in clients)
    total_disk = sum(float(c.get("total_disk_mb") or 0) for c in clients)
    n          = len(clients)

    tenant_rows = []
    for c in clients:
        rev  = _calc_revenue(c.get("plan") or "free",
                             c.get("billing_interval") or "yearly",
                             plan_ec, cs)
        cost = _calc_infra_cost(c, cs, total_cpu, total_ram, total_disk, n)
        total_cost  = round(sum(cost.values()), 2)
        net_rev     = rev["net_monthly_revenue"]
        profit      = round(net_rev - total_cost, 2)
        margin_pct  = round((profit / net_rev * 100) if net_rev > 0 else -100.0, 1)
        rec, reason = _recommendation(c, plan_ec, margin_pct)
        tenant_rows.append({**c, **rev, **cost,
                            "total_cost_usd": total_cost,
                            "profit_usd": profit,
                            "margin_percent": margin_pct,
                            "recommendation": rec, "reason": reason})

    mrr_gross = round(sum(r["gross_monthly_revenue"] for r in tenant_rows), 2)
    mrr_net   = round(sum(r["net_monthly_revenue"] for r in tenant_rows), 2)
    total_infra = cs.get("monthly_server_cost_usd") or 18.98
    variable_cost = round(sum(r.get("backup_cost_usd", 0) for r in tenant_rows), 2)
    monthly_total = round(total_infra + variable_cost, 2)
    profit_total  = round(mrr_net - monthly_total, 2)
    gross_margin  = round((profit_total / mrr_net * 100) if mrr_net > 0 else -100.0, 1)
    break_even_gap = round(max(0.0, monthly_total - mrr_net), 2)

    profitable_count   = sum(1 for r in tenant_rows if r["profit_usd"] >= 0)
    unprofitable_count = sum(1 for r in tenant_rows if r["profit_usd"] < 0)

    # Customers needed per plan to cover break-even gap
    def _needed(plan_name: str) -> int:
        if break_even_gap <= 0:
            return 0
        rev = _calc_revenue(plan_name, "yearly", plan_ec, cs)
        net = rev["net_monthly_revenue"]
        if net <= 0:
            return 999
        per_client_cost = monthly_total / max(1, n + 1)
        net_contribution = net - per_client_cost
        if net_contribution <= 0:
            return 999
        return math.ceil(break_even_gap / net_contribution)

    by_plan = {p: _needed(p) for p in ("personal", "negocio", "agencia", "agencia_pro")}

    top_profitable = sorted(tenant_rows, key=lambda x: x["profit_usd"], reverse=True)[:5]
    top_expensive  = sorted(tenant_rows, key=lambda x: x["total_cost_usd"], reverse=True)[:5]
    upgrade_rec    = [r for r in tenant_rows if r["recommendation"] in
                      ("upgrade_recommended", "possible_abuse", "unprofitable")][:10]

    def _slim(r: dict) -> dict:
        return {k: r[k] for k in
                ("user_id","email","plan","profit_usd","total_cost_usd",
                 "gross_monthly_revenue","net_monthly_revenue","margin_percent",
                 "recommendation","reason","hosting_count")}

    return {
        "am_i_profitable":            profit_total > 0,
        "mrr_gross":                  mrr_gross,
        "mrr_net":                    mrr_net,
        "monthly_fixed_cost":         round(total_infra, 2),
        "monthly_variable_cost":      variable_cost,
        "monthly_total_cost":         monthly_total,
        "estimated_profit":           profit_total,
        "gross_margin_percent":       gross_margin,
        "break_even_gap_usd":         break_even_gap,
        "profitable_customers_count": profitable_count,
        "unprofitable_customers_count": unprofitable_count,
        "customers_needed_for_break_even_by_plan": by_plan,
        "top_profitable_customers":   [_slim(r) for r in top_profitable],
        "top_expensive_customers":    [_slim(r) for r in top_expensive],
        "upgrade_recommended_customers": [_slim(r) for r in upgrade_rec],
        "total_clients":              n,
    }
