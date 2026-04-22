"""Tests for authentication endpoints and the require_auth dependency."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

TEST_SECRET = "test-secret-key-exactly-32-chars!!"
ADMIN_EMAIL = "admin@empresa.com"
ADMIN_PWD = "TestAdminPass123"


@pytest.fixture(autouse=True)
def auth_setup(tmp_path, monkeypatch):
    """Patch DB to a temp file, skip seed, set AUTH_SECRET, insert one admin user."""
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("AUTH_SECRET", TEST_SECRET)

    db_file = tmp_path / "auth_test.sqlite"
    import app.auth.models as m
    monkeypatch.setattr(m, "DB_PATH", db_file)
    m.init_db()
    m.create_user(
        email=ADMIN_EMAIL,
        full_name="Admin Beta",
        role="admin",
        hashed_password=m.hash_password(ADMIN_PWD),
    )


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app)


# ── /auth/login ──────────────────────────────────────────────────────────────

def test_login_valid(client):
    resp = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_invalid_password(client):
    resp = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": "wrongpass"})
    assert resp.status_code == 401
    assert "Credenciales incorrectas" in resp.json()["detail"]


def test_login_unknown_email(client):
    resp = client.post("/auth/login", json={"email": "noone@intecsaindustrial.com", "password": "anything"})
    assert resp.status_code == 401


# ── /auth/me ─────────────────────────────────────────────────────────────────

def test_me_with_bearer_token(client):
    token = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}).json()["access_token"]
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == ADMIN_EMAIL
    assert body["role"] == "admin"


def test_me_with_cookie(client):
    """Simulates the browser httpOnly cookie transport used in production."""
    token = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}).json()["access_token"]
    resp = client.get("/auth/me", cookies={"auth_token": token})
    assert resp.status_code == 200
    assert resp.json()["email"] == ADMIN_EMAIL


def test_me_without_auth(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


# ── Protected routes ──────────────────────────────────────────────────────────

def test_projects_requires_auth(client):
    resp = client.get("/projects")
    assert resp.status_code == 401


def test_query_requires_auth(client):
    resp = client.post("/query", json={"query": "test"})
    assert resp.status_code == 401


def test_health_open(client):
    """Health endpoint must remain open — no auth required."""
    resp = client.get("/health")
    assert resp.status_code == 200
