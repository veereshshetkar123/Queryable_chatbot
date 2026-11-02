"""Admin console API."""

import pytest

from backend import admin
from backend.auth import create_user, sessions, users

ADMIN = {"username": "boss", "password": "admin-password-123"}


@pytest.fixture()
def admin_client(app_client, user):
    users.delete_many({"username": {"$in": ["boss", "newbie", "boss2"]}})
    admin.audit_log.delete_many({})
    create_user(ADMIN["username"], ADMIN["password"], "The Boss", role="admin")
    assert app_client.post("/api/auth/login", json=ADMIN).status_code == 200
    yield app_client
    users.delete_many({"username": {"$in": ["boss", "newbie", "boss2"]}})
    sessions.delete_many({"username": {"$in": ["boss", "newbie", "boss2"]}})
    admin.audit_log.delete_many({})


def test_analysts_are_forbidden(logged_in):
    for url in ("/api/admin/overview", "/api/admin/users", "/api/admin/audit"):
        assert logged_in.get(url).status_code == 403


def test_overview_shape(admin_client):
    body = admin_client.get("/api/admin/overview").json()
    assert body["kpis"]["users"] >= 2
    assert body["kpis"]["admins"] >= 1
    assert len(body["days"]) == 14
    assert {plan["id"] for plan in body["plans"]} == {"free", "pro", "team"}
    assert body["system"]["mongodb"] is True


def test_list_users_has_no_secrets(admin_client):
    body = admin_client.get("/api/admin/users").json()
    names = {u["username"]: u for u in body["users"]}
    assert {"boss", "tester"} <= set(names)
    assert "password_hash" not in names["tester"]
    assert names["boss"]["signed_in"] is True
    assert body["me"] == "boss"
    assert admin_client.get("/api/admin/users", params={"q": "TEST"}).json()["users"][0]["username"] == "tester"


def test_create_update_and_audit(admin_client):
    created = admin_client.post("/api/admin/users", json={
        "username": "Newbie", "password": "long-enough-pw", "display_name": "New  Person", "plan": "pro",
    })
    assert created.status_code == 201
    doc = users.find_one({"username": "newbie"})
    assert doc["plan"] == "pro" and doc["display_name"] == "New Person" and doc["role"] == "analyst"

    assert admin_client.post("/api/admin/users", json={"username": "newbie", "password": "long-enough-pw"}).status_code == 409

    updated = admin_client.patch("/api/admin/users/newbie", json={"role": "admin", "plan": "team"}).json()
    assert updated["role"] == "admin" and updated["plan"] == "team"

    actions = [event["action"] for event in admin_client.get("/api/admin/audit").json()["events"]]
    assert actions[:2] == ["user.update", "user.create"]


def test_disable_signs_the_user_out(admin_client, user):
    from fastapi.testclient import TestClient

    import backend.main as main

    with TestClient(main.app) as other:
        assert other.post("/api/auth/login", json=user).status_code == 200
        assert other.get("/api/auth/me").status_code == 200
        assert admin_client.patch("/api/admin/users/tester", json={"disabled": True}).json()["disabled"] is True
        assert other.get("/api/auth/me").status_code == 401
        assert other.post("/api/auth/login", json=user).status_code == 401
    admin_client.patch("/api/admin/users/tester", json={"disabled": False})


def test_admin_cannot_lock_themselves_out(admin_client):
    users.update_many({"role": "admin", "username": {"$ne": "boss"}}, {"$set": {"role": "analyst"}})
    assert admin_client.patch("/api/admin/users/boss", json={"disabled": True}).status_code == 400
    assert admin_client.patch("/api/admin/users/boss", json={"role": "analyst"}).status_code == 400

    # Another admin can't remove the last active one either.
    create_user("boss2", "admin-password-456", role="admin")
    admin_client.patch("/api/admin/users/boss2", json={"disabled": True})
    assert users.find_one({"username": "boss2"})["disabled"] is True


def test_password_reset(admin_client, user):
    response = admin_client.post("/api/admin/users/tester/password", json={"new_password": "brand-new-password"})
    assert response.status_code == 200
    login = admin_client.post("/api/auth/login", json={"username": "tester", "password": "brand-new-password"})
    assert login.status_code == 200
