"""
Tests for free-plan business policy:
  - Global free user cap (MAX_FREE_USERS = 10)
  - 30-day recreation protection
  - Expiration cleanup: docker rm + soft-delete
  - User is never deleted
  - Job idempotency (running twice is safe)
"""
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call


# ─── shared mock helpers ──────────────────────────────────────────────────────

def _mock_conn(fetchone=None, fetchall=None, rowcount=1):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone
    cursor.fetchall.return_value = fetchall or []
    cursor.rowcount = rowcount
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


PATCH_CONN    = "app.infra.audit.hosting_repository.get_connection"
PATCH_RELEASE = "app.infra.audit.hosting_repository.release_connection"


# ─── count_active_free_users ─────────────────────────────────────────────────

def test_count_active_free_users_returns_count():
    from app.infra.audit.hosting_repository import HostingRepository

    conn, cursor = _mock_conn(fetchone={"cnt": 7})
    with patch(PATCH_CONN, return_value=conn), patch(PATCH_RELEASE):
        result = HostingRepository().count_active_free_users()

    assert result == 7


def test_count_active_free_users_empty():
    from app.infra.audit.hosting_repository import HostingRepository

    conn, cursor = _mock_conn(fetchone={"cnt": 0})
    with patch(PATCH_CONN, return_value=conn), patch(PATCH_RELEASE):
        result = HostingRepository().count_active_free_users()

    assert result == 0


# ─── Global cap enforcement ───────────────────────────────────────────────────

def _verified_user(user_id: int) -> dict:
    """Return a mock user dict that passes the email_verified gate."""
    return {"user_id": user_id, "email": "test@t.com", "email_verified": 1,
            "plan": "free", "role": "user"}


def _stub_hosting_repo(count_free_users=0, had_recent=False):
    """Return a fully-mocked hosting_repo for create-hosting tests."""
    mock = MagicMock()
    mock.count_active_free_users.return_value = count_free_users
    mock.had_free_hosting_recently.return_value = had_recent
    mock.has_free_plan_from_ip.return_value = False
    mock.count_active_hostings.return_value = 0
    return mock


def test_create_hosting_blocked_when_global_cap_reached(tc, db_mocks):
    """create_hosting returns 503 when 10 free users are already active."""
    login = tc.post("/login", json={"email": db_mocks["client_email"], "password": db_mocks["client_pw"]})
    assert login.status_code == 200
    client_id = db_mocks["client_id"]

    with patch("app.api.routes.hosting._user_repo") as mock_ur, \
         patch("app.api.routes.hosting.hosting_repo", _stub_hosting_repo(count_free_users=10)):
        mock_ur.get_user_by_id.return_value = _verified_user(client_id)
        tc.cookies.update(login.cookies)
        resp = tc.post("/create-hosting", json={"name": "my-site", "plan": "free"})

    assert resp.status_code == 503
    assert "capacity" in resp.json()["detail"].lower()


# ─── 30-day recreation protection ────────────────────────────────────────────

def test_had_free_hosting_recently_true():
    from app.infra.audit.hosting_repository import HostingRepository

    conn, cursor = _mock_conn(fetchone={"1": 1})
    with patch(PATCH_CONN, return_value=conn), patch(PATCH_RELEASE):
        result = HostingRepository().had_free_hosting_recently(user_id=42)

    assert result is True


def test_had_free_hosting_recently_false():
    from app.infra.audit.hosting_repository import HostingRepository

    conn, cursor = _mock_conn(fetchone=None)
    with patch(PATCH_CONN, return_value=conn), patch(PATCH_RELEASE):
        result = HostingRepository().had_free_hosting_recently(user_id=42)

    assert result is False


def test_create_hosting_blocked_by_recent_free_history(tc, db_mocks):
    """create_hosting returns 403 when user had a free site in the last 30 days."""
    login = tc.post("/login", json={"email": db_mocks["client_email"], "password": db_mocks["client_pw"]})
    assert login.status_code == 200
    client_id = db_mocks["client_id"]

    with patch("app.api.routes.hosting._user_repo") as mock_ur, \
         patch("app.api.routes.hosting.hosting_repo", _stub_hosting_repo(had_recent=True)):
        mock_ur.get_user_by_id.return_value = _verified_user(client_id)
        tc.cookies.update(login.cookies)
        resp = tc.post("/create-hosting", json={"name": "my-site", "plan": "free"})

    assert resp.status_code == 403
    assert "30" in resp.json()["detail"]


# ─── Expiration status change ─────────────────────────────────────────────────

def test_expiration_changes_status_to_expired():
    """_expire_single marks the hosting as expired on docker stop success."""
    from app.services.expiration_job import _expire_single

    hosting = {
        "hosting_id": 1,
        "container_name": "user_1_test_abc123",
        "user_id": 1,
    }

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("app.services.expiration_job.subprocess.run", return_value=mock_result) as mock_run, \
         patch("app.services.expiration_job.HostingRepository") as MockRepo:
        repo_instance = MockRepo.return_value
        h, success = _expire_single(hosting)

    assert success is True
    repo_instance.update_hosting_status.assert_any_call(1, "expiring")
    repo_instance.update_hosting_status.assert_any_call(1, "expired")


# ─── Cleanup: docker rm + soft-delete ────────────────────────────────────────

def test_cleanup_expired_calls_docker_rm_and_marks_deleted():
    """_cleanup_expired_hostings calls docker rm and mark_deleted for each expired hosting."""
    from app.services.expiration_job import _cleanup_expired_hostings

    expired = [
        {"hosting_id": 10, "container_name": "user_1_site_aaa", "user_id": 1},
        {"hosting_id": 11, "container_name": "user_2_site_bbb", "user_id": 2},
    ]

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("app.services.expiration_job.subprocess.run", return_value=mock_result) as mock_run, \
         patch("app.services.expiration_job.HostingRepository") as MockRepo:
        repo_instance = MockRepo.return_value
        # First call returns 2 items, second call returns empty (end of pagination)
        repo_instance.get_expired_hostings.side_effect = [expired, []]

        count = _cleanup_expired_hostings()

    assert count == 2
    # docker rm -f called for each container
    containers_passed = [c.args[0][3] for c in mock_run.call_args_list]
    assert "user_1_site_aaa" in containers_passed
    assert "user_2_site_bbb" in containers_passed
    # soft-delete called for each
    repo_instance.mark_deleted.assert_any_call(10)
    repo_instance.mark_deleted.assert_any_call(11)


def test_cleanup_ignores_docker_rm_failure():
    """Cleanup continues and soft-deletes even when docker rm returns non-zero."""
    from app.services.expiration_job import _cleanup_expired_hostings

    expired = [{"hosting_id": 20, "container_name": "user_3_gone_xyz", "user_id": 3}]

    mock_result = MagicMock()
    mock_result.returncode = 1  # container already gone
    mock_result.stderr = b""

    with patch("app.services.expiration_job.subprocess.run", return_value=mock_result), \
         patch("app.services.expiration_job.HostingRepository") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_expired_hostings.side_effect = [expired, []]

        count = _cleanup_expired_hostings()

    assert count == 1
    repo_instance.mark_deleted.assert_called_once_with(20)


# ─── User is never deleted ────────────────────────────────────────────────────

def test_user_not_deleted_during_cleanup():
    """Cleanup never calls any user-deletion method."""
    from app.services.expiration_job import _cleanup_expired_hostings

    expired = [{"hosting_id": 30, "container_name": "user_4_site_qqq", "user_id": 4}]

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("app.services.expiration_job.subprocess.run", return_value=mock_result), \
         patch("app.services.expiration_job.HostingRepository") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.get_expired_hostings.side_effect = [expired, []]
        _cleanup_expired_hostings()

    # None of the user-deletion methods should have been called
    assert not repo_instance.delete_user.called
    assert not repo_instance.admin_delete_user.called


# ─── Idempotency ─────────────────────────────────────────────────────────────

def test_cleanup_idempotent_second_run_finds_nothing():
    """Running cleanup twice is safe: second run finds no expired hostings."""
    from app.services.expiration_job import _cleanup_expired_hostings

    with patch("app.services.expiration_job.subprocess.run") as mock_run, \
         patch("app.services.expiration_job.HostingRepository") as MockRepo:
        repo_instance = MockRepo.return_value
        # Both calls return empty — nothing to clean up
        repo_instance.get_expired_hostings.return_value = []

        count1 = _cleanup_expired_hostings()
        count2 = _cleanup_expired_hostings()

    assert count1 == 0
    assert count2 == 0
    mock_run.assert_not_called()
    repo_instance.mark_deleted.assert_not_called()


# ─── mark_deleted sets deleted_at ────────────────────────────────────────────

def test_mark_deleted_sets_status_and_timestamp():
    from app.infra.audit.hosting_repository import HostingRepository

    conn, cursor = _mock_conn(rowcount=1)
    with patch(PATCH_CONN, return_value=conn), patch(PATCH_RELEASE):
        result = HostingRepository().mark_deleted(hosting_id=99)

    assert result is True
    sql_called = cursor.execute.call_args[0][0]
    assert "deleted_at" in sql_called
    assert "status" in sql_called
