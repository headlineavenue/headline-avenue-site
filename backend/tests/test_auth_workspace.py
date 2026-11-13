import os
from pathlib import Path

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///./headline_avenue_test.db"
os.environ["AUTH_COOKIE_SECURE"] = "false"
os.environ["TOKEN_ENCRYPTION_KEY"] = "vP3YScmTVY-fyL7pLvsoGNNJV0iA0Qvj60p6UfLSCK4="

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


DB_PATH = Path("headline_avenue_test.db")


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def register(client: TestClient, email: str, name: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": name,
            "workspace_name": f"{name} Workspace",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["csrf_token"]
    assert payload["active_workspace_id"]
    assert payload["user"]["email"] == email
    return payload


def test_register_me_logout_session() -> None:
    reset_database()
    with TestClient(app) as client:
        session = register(client, "owner@example.com", "Owner")
        assert client.cookies.get("ha_session")

        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text
        refreshed = me.json()
        assert refreshed["user"]["display_name"] == "Owner"
        assert refreshed["csrf_token"]

        logout = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": refreshed["csrf_token"]},
        )
        assert logout.status_code == 204

        after = client.get("/api/v1/auth/me")
        assert after.status_code == 401


def test_workspace_isolation_blocks_cross_tenant_reads() -> None:
    reset_database()
    with TestClient(app) as owner_a, TestClient(app) as owner_b:
        session_a = register(owner_a, "a@example.com", "Alpha")
        workspace_a = session_a["active_workspace_id"]

        created = owner_a.post(
            "/api/v1/sources",
            headers={
                "X-Workspace-ID": workspace_a,
                "X-CSRF-Token": session_a["csrf_token"],
            },
            json={
                "kind": "transcript",
                "title": "Private Alpha Source",
                "transcript_text": "This source belongs only to Alpha workspace.",
            },
        )
        assert created.status_code == 201, created.text
        source_id = created.json()["id"]

        session_b = register(owner_b, "b@example.com", "Beta")
        workspace_b = session_b["active_workspace_id"]

        foreign_by_own_workspace = owner_b.get(
            f"/api/v1/sources/{source_id}",
            headers={"X-Workspace-ID": workspace_b},
        )
        assert foreign_by_own_workspace.status_code == 404

        foreign_workspace_header = owner_b.get(
            f"/api/v1/sources/{source_id}",
            headers={"X-Workspace-ID": workspace_a},
        )
        assert foreign_workspace_header.status_code == 404

        listing = owner_b.get(
            "/api/v1/sources",
            headers={"X-Workspace-ID": workspace_b},
        )
        assert listing.status_code == 200
        assert all(item["id"] != source_id for item in listing.json())


def test_workspace_header_is_required_for_product_api() -> None:
    reset_database()
    with TestClient(app) as client:
        register(client, "required@example.com", "Required")
        response = client.get("/api/v1/sources")
        assert response.status_code == 400
        assert response.json()["detail"] == "X-Workspace-ID header is required"


def test_authenticated_mutation_requires_csrf() -> None:
    reset_database()
    with TestClient(app) as client:
        session = register(client, "csrf@example.com", "CSRF")
        workspace_id = session["active_workspace_id"]

        blocked = client.post(
            "/api/v1/sources",
            headers={"X-Workspace-ID": workspace_id},
            json={
                "kind": "transcript",
                "title": "Blocked Source",
                "transcript_text": "This write should require a CSRF token.",
            },
        )
        assert blocked.status_code == 403

        allowed = client.post(
            "/api/v1/sources",
            headers={
                "X-Workspace-ID": workspace_id,
                "X-CSRF-Token": session["csrf_token"],
            },
            json={
                "kind": "transcript",
                "title": "Allowed Source",
                "transcript_text": "This write includes the session CSRF token.",
            },
        )
        assert allowed.status_code == 201, allowed.text
