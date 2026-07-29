"""User management, password policy and sign-in throttling."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["PAPERLESS_AOT_DB"] = os.path.join(
    os.path.dirname(__file__), "test_users.db")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.services import auth as auth_service  # noqa: E402

STRONG = "Cargo2026x"
ANOTHER = "Manifest99z"


@pytest.fixture(scope="module")
def admin():
    os.environ["PAPERLESS_AOT_DB"] = os.path.join(
        os.path.dirname(__file__), "test_users.db")
    if os.path.exists(os.environ["PAPERLESS_AOT_DB"]):
        os.remove(os.environ["PAPERLESS_AOT_DB"])
    from app.database import db, init_db
    from app.services.auth import ensure_default_users
    init_db()
    with db() as conn:
        ensure_default_users(conn)
    c = TestClient(main.app)
    c.post("/api/v1/auth/login",
           json={"username": "admin", "password": "admin123"})
    yield c
    os.remove(os.environ["PAPERLESS_AOT_DB"])


def fresh_client():
    return TestClient(main.app)


class TestPasswordPolicy:
    @pytest.mark.parametrize("password,reason", [
        ("short1", "too short"),
        ("admin123", "on the weak list"),
        ("abcdefghij", "letters only"),
        ("1234567890", "digits only"),
    ])
    def test_rejected(self, password, reason):
        with pytest.raises(auth_service.PasswordError):
            auth_service.validate_password(password, "someone")

    def test_rejects_password_equal_to_username(self):
        with pytest.raises(auth_service.PasswordError):
            auth_service.validate_password("operator1", "Operator1")

    def test_accepts_a_reasonable_password(self):
        assert auth_service.validate_password(STRONG, "admin") == STRONG


class TestForcedChange:
    def test_seeded_accounts_must_change(self, admin):
        me = admin.get("/api/v1/auth/me").json()["user"]
        assert me["mustChangePassword"] is True

    def test_change_clears_the_flag_and_ends_sessions(self):
        c = fresh_client()
        c.post("/api/v1/auth/login",
               json={"username": "viewer", "password": "viewer123"})
        r = c.post("/api/v1/auth/password", json={
            "currentPassword": "viewer123", "newPassword": STRONG})
        assert r.status_code == 200
        assert r.json()["reloginRequired"] is True

        # the old session is gone
        assert c.get("/api/v1/auth/me").status_code == 401

        # the old password no longer works, the new one does
        again = fresh_client()
        assert again.post("/api/v1/auth/login", json={
            "username": "viewer", "password": "viewer123"}).status_code == 401
        ok = again.post("/api/v1/auth/login",
                        json={"username": "viewer", "password": STRONG})
        assert ok.status_code == 200
        assert ok.json()["user"]["mustChangePassword"] is False

    def test_wrong_current_password_is_rejected(self, admin):
        r = admin.post("/api/v1/auth/password", json={
            "currentPassword": "nope", "newPassword": ANOTHER})
        assert r.status_code == 401

    def test_new_password_must_differ(self):
        c = fresh_client()
        c.post("/api/v1/auth/login",
               json={"username": "operator", "password": "operator123"})
        r = c.post("/api/v1/auth/password", json={
            "currentPassword": "operator123", "newPassword": "operator123"})
        assert r.status_code == 400

    def test_weak_new_password_is_rejected(self):
        c = fresh_client()
        c.post("/api/v1/auth/login",
               json={"username": "operator", "password": "operator123"})
        r = c.post("/api/v1/auth/password", json={
            "currentPassword": "operator123", "newPassword": "password"})
        assert r.status_code == 400
        assert r.json()["code"] == "WEAK_PASSWORD"


class TestUserAdministration:
    def test_create_and_sign_in(self, admin):
        r = admin.post("/api/v1/users", json={
            "username": "somchai", "password": STRONG,
            "role": "OPERATOR", "displayName": "Somchai R."})
        assert r.status_code == 200

        c = fresh_client()
        login = c.post("/api/v1/auth/login",
                       json={"username": "somchai", "password": STRONG})
        assert login.status_code == 200
        # a new account starts out having to pick its own password
        assert login.json()["user"]["mustChangePassword"] is True
        assert login.json()["user"]["role"] == "OPERATOR"

    def test_duplicate_username_rejected(self, admin):
        r = admin.post("/api/v1/users", json={
            "username": "somchai", "password": ANOTHER, "role": "VIEWER"})
        assert r.status_code == 400

    @pytest.mark.parametrize("username", ["ab", "Has Space", "sym!bol", ""])
    def test_invalid_usernames_rejected(self, admin, username):
        r = admin.post("/api/v1/users", json={
            "username": username, "password": ANOTHER, "role": "VIEWER"})
        assert r.status_code == 400

    def test_weak_password_rejected_on_create(self, admin):
        r = admin.post("/api/v1/users", json={
            "username": "weakling", "password": "12345678", "role": "VIEWER"})
        assert r.status_code == 400

    def test_role_change_and_deactivate(self, admin):
        users = admin.get("/api/v1/users").json()["items"]
        somchai = next(u for u in users if u["username"] == "somchai")

        assert admin.patch(f"/api/v1/users/{somchai['id']}",
                           json={"role": "VIEWER"}).status_code == 200
        assert admin.patch(f"/api/v1/users/{somchai['id']}",
                           json={"active": False}).status_code == 200

        # a deactivated account cannot sign in
        c = fresh_client()
        assert c.post("/api/v1/auth/login", json={
            "username": "somchai", "password": STRONG}).status_code == 401

    def test_admin_cannot_deactivate_themselves(self, admin):
        me = admin.get("/api/v1/auth/me").json()["user"]
        r = admin.patch(f"/api/v1/users/{me['id']}", json={"active": False})
        assert r.status_code == 400

    def test_last_administrator_is_protected(self, admin):
        me = admin.get("/api/v1/auth/me").json()["user"]
        r = admin.patch(f"/api/v1/users/{me['id']}", json={"role": "VIEWER"})
        assert r.status_code == 400
        assert "Administrator" in r.json()["message"]

    def test_reset_forces_a_change(self, admin):
        users = admin.get("/api/v1/users").json()["items"]
        operator = next(u for u in users if u["username"] == "operator")
        r = admin.post(f"/api/v1/users/{operator['id']}/password",
                       json={"newPassword": ANOTHER})
        assert r.json()["mustChangePassword"] is True

        c = fresh_client()
        login = c.post("/api/v1/auth/login",
                       json={"username": "operator", "password": ANOTHER})
        assert login.json()["user"]["mustChangePassword"] is True

    def test_non_admins_are_locked_out_of_user_management(self, admin):
        c = fresh_client()
        c.post("/api/v1/auth/login",
               json={"username": "viewer", "password": STRONG})
        assert c.get("/api/v1/users").status_code == 403
        assert c.post("/api/v1/users", json={
            "username": "sneaky", "password": ANOTHER,
            "role": "ADMINISTRATOR"}).status_code == 403
        me = c.get("/api/v1/auth/me").json()["user"]
        assert c.post(f"/api/v1/users/{me['id']}/password",
                      json={"newPassword": ANOTHER}).status_code == 403


class TestLoginThrottling:
    def test_lockout_after_repeated_failures(self, admin):
        admin.post("/api/v1/users", json={
            "username": "lockme", "password": STRONG, "role": "VIEWER"})
        c = fresh_client()
        for _ in range(auth_service.MAX_FAILED_ATTEMPTS):
            r = c.post("/api/v1/auth/login",
                       json={"username": "lockme", "password": "wrong-one"})
            assert r.status_code == 401

        blocked = c.post("/api/v1/auth/login",
                         json={"username": "lockme", "password": STRONG})
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "TOO_MANY_ATTEMPTS"

    def test_lockout_is_per_account(self, admin):
        """Locking one account must not lock everyone else out."""
        c = fresh_client()
        r = c.post("/api/v1/auth/login",
                   json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200

    def test_attempts_are_recorded(self, admin):
        rows = admin.get("/api/v1/data/login_attempts", params={
            "filter": ["username:eq:lockme"]}).json()
        assert rows["total"] >= auth_service.MAX_FAILED_ATTEMPTS
        assert all(r["success"] == 0 for r in rows["rows"])
