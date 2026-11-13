import os
import shutil
from pathlib import Path

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///./headline_avenue_test.db"
os.environ["AUTH_COOKIE_SECURE"] = "false"
os.environ["TOKEN_ENCRYPTION_KEY"] = "vP3YScmTVY-fyL7pLvsoGNNJV0iA0Qvj60p6UfLSCK4="
os.environ["MEDIA_STORAGE_BACKEND"] = "local"
os.environ["MEDIA_LOCAL_DIR"] = "./test_uploads"
os.environ["MEDIA_MAX_UPLOAD_MB"] = "5"

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


DB_PATH = Path("headline_avenue_test.db")
UPLOAD_ROOT = Path("test_uploads")


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    shutil.rmtree(UPLOAD_ROOT, ignore_errors=True)


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


def test_me_does_not_invalidate_existing_csrf_token() -> None:
    reset_database()
    with TestClient(app) as client:
        session = register(client, "tabs@example.com", "Tabs")
        original_csrf = session["csrf_token"]
        workspace_id = session["active_workspace_id"]

        first_me = client.get("/api/v1/auth/me")
        second_me = client.get("/api/v1/auth/me")
        assert first_me.status_code == 200
        assert second_me.status_code == 200
        assert first_me.json()["csrf_token"] == original_csrf
        assert second_me.json()["csrf_token"] == original_csrf

        write = client.post(
            "/api/v1/sources",
            headers={
                "X-Workspace-ID": workspace_id,
                "X-CSRF-Token": original_csrf,
            },
            json={
                "kind": "transcript",
                "title": "Multi-tab safe source",
                "transcript_text": "The original CSRF token remains valid after repeated session reads.",
            },
        )
        assert write.status_code == 201, write.text


def test_custom_domain_cors_allows_credentials() -> None:
    reset_database()
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/auth/me",
            headers={
                "Origin": "https://headlineavenue.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200, response.text
        assert response.headers["access-control-allow-origin"] == "https://headlineavenue.com"
        assert response.headers["access-control-allow-credentials"] == "true"


def test_production_registration_defaults_closed() -> None:
    from app.config import Settings

    production = Settings(
        app_env="production",
        auth_registration_enabled=None,
        _env_file=None,
    )
    development = Settings(
        app_env="development",
        auth_registration_enabled=None,
        _env_file=None,
    )
    assert production.registration_enabled is False
    assert development.registration_enabled is True


def test_story_desk_uses_authenticated_workspace_data() -> None:
    reset_database()
    with TestClient(app) as client:
        session = register(client, "desk@example.com", "Desk")
        workspace_id = session["active_workspace_id"]
        headers = {
            "X-Workspace-ID": workspace_id,
            "X-CSRF-Token": session["csrf_token"],
        }

        source = client.post(
            "/api/v1/sources",
            headers=headers,
            json={
                "kind": "transcript",
                "title": "Desk test transcript",
                "transcript_text": (
                    "Headline Avenue is testing the real Story Desk. "
                    "The authenticated workspace should show this persisted story "
                    "and should not display prototype newsroom rows."
                ),
            },
        )
        assert source.status_code == 201, source.text
        source_id = source.json()["id"]

        story = client.post(
            "/api/v1/stories",
            headers=headers,
            json={
                "source_id": source_id,
                "title": "Authenticated Story Desk test",
            },
        )
        assert story.status_code == 201, story.text
        story_id = story.json()["id"]

        analyzed = client.post(
            f"/api/v1/stories/{story_id}/analyze",
            headers=headers,
        )
        assert analyzed.status_code == 200, analyzed.text

        desk = client.get(
            "/api/v1/stories/desk",
            headers={"X-Workspace-ID": workspace_id},
        )
        assert desk.status_code == 200, desk.text
        payload = desk.json()
        assert payload["total"] == 1
        assert payload["active"] == 1
        assert payload["needs_review"] == 0
        assert payload["scheduled"] == 0
        assert len(payload["stories"]) == 1

        item = payload["stories"][0]
        assert item["id"] == story_id
        assert item["source_id"] == source_id
        assert item["title"] == "Authenticated Story Desk test"
        assert item["source_title"] == "Desk test transcript"
        assert item["source_kind"] == "transcript"
        assert item["sourceguard_status"] == "supported"
        assert item["publish_status"] == "drafting"
        assert item["output_count"] == 0


def test_binary_media_upload_is_private_workspace_source() -> None:
    reset_database()
    with TestClient(app) as client:
        session = register(client, "media@example.com", "Media")
        workspace_id = session["active_workspace_id"]
        headers = {
            "X-Workspace-ID": workspace_id,
            "X-CSRF-Token": session["csrf_token"],
        }

        payload = b"fake-mp4-payload-for-private-storage"
        response = client.post(
            "/api/v1/sources/upload",
            headers=headers,
            data={"kind": "video"},
            files={"file": ("interview.mp4", payload, "video/mp4")},
        )
        assert response.status_code == 201, response.text
        source = response.json()
        assert source["kind"] == "video"
        assert source["status"] == "uploaded"

        media = source["metadata_json"]["media"]
        assert media["backend"] == "local"
        assert media["filename"] == "interview.mp4"
        assert media["content_type"] == "video/mp4"
        assert media["size"] == len(payload)
        assert media["private"] is True
        assert media["sha256"]

        stored_path = UPLOAD_ROOT / media["key"]
        assert stored_path.exists()
        assert stored_path.read_bytes() == payload

        library = client.get(
            "/api/v1/sources/library",
            headers={"X-Workspace-ID": workspace_id},
        )
        assert library.status_code == 200, library.text
        library_payload = library.json()
        assert library_payload["total"] == 1
        assert library_payload["uploaded"] == 1
        assert library_payload["indexed"] == 0
        assert library_payload["needs_attention"] == 0
        item = library_payload["sources"][0]
        assert item["id"] == source["id"]
        assert item["storage_filename"] == "interview.mp4"
        assert item["storage_size"] == len(payload)
        assert item["has_transcript"] is False


def test_media_upload_rejects_wrong_content_type() -> None:
    reset_database()
    with TestClient(app) as client:
        session = register(client, "badmedia@example.com", "BadMedia")
        headers = {
            "X-Workspace-ID": session["active_workspace_id"],
            "X-CSRF-Token": session["csrf_token"],
        }
        response = client.post(
            "/api/v1/sources/upload",
            headers=headers,
            data={"kind": "audio"},
            files={"file": ("not-audio.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 400
