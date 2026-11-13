from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4

import psycopg


DATABASE_URL = os.environ["MIGRATION_TEST_DATABASE_URL"]
LEGACY_WORKSPACE_ID = str(uuid4())
SECOND_WORKSPACE_ID = str(uuid4())
LEGACY_CONNECTION_ID = str(uuid4())


def run(sql: str, params: tuple | None = None) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()


def scalar(sql: str, params: tuple | None = None):
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            return row[0] if row else None


def reset_legacy_schema() -> None:
    run("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    run(
        """
        CREATE TABLE workspaces (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(160) NOT NULL,
            slug VARCHAR(120) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL
        );
        """
    )
    run(
        """
        CREATE TABLE platform_connections (
            id VARCHAR(36) PRIMARY KEY,
            provider VARCHAR(40) NOT NULL UNIQUE,
            status VARCHAR(40) NOT NULL,
            account_id VARCHAR(255),
            display_name VARCHAR(255),
            avatar_url TEXT,
            scope TEXT,
            access_token TEXT,
            refresh_token TEXT,
            access_expires_at TIMESTAMPTZ,
            refresh_expires_at TIMESTAMPTZ,
            metadata_json JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        );
        """
    )

    now = datetime.now(timezone.utc)
    run(
        "INSERT INTO workspaces (id, name, slug, created_at) VALUES (%s, %s, %s, %s)",
        (LEGACY_WORKSPACE_ID, "Demo Workspace", "demo", now),
    )
    run(
        """
        INSERT INTO platform_connections (
            id, provider, status, account_id, display_name, scope,
            access_token, refresh_token, metadata_json, created_at, updated_at
        ) VALUES (%s, 'tiktok', 'connected', 'legacy-open-id', 'Headline Avenue',
                  'user.info.basic', 'legacy-access-token', 'legacy-refresh-token',
                  '{}'::json, %s, %s)
        """,
        (LEGACY_CONNECTION_ID, now, now),
    )


def migrate() -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    env["APP_ENV"] = "test"
    env["TOKEN_ENCRYPTION_KEY"] = "vP3YScmTVY-fyL7pLvsoGNNJV0iA0Qvj60p6UfLSCK4="

    subprocess.run(
        [sys.executable, "-m", "app.bootstrap_db"],
        check=True,
        env=env,
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=env,
    )


def verify() -> None:
    workspace_id = scalar(
        "SELECT workspace_id FROM platform_connections WHERE id = %s",
        (LEGACY_CONNECTION_ID,),
    )
    assert workspace_id == LEGACY_WORKSPACE_ID, workspace_id

    account_id = scalar(
        "SELECT account_id FROM platform_connections WHERE id = %s",
        (LEGACY_CONNECTION_ID,),
    )
    assert account_id == "legacy-open-id"

    access_token = scalar(
        "SELECT access_token FROM platform_connections WHERE id = %s",
        (LEGACY_CONNECTION_ID,),
    )
    assert access_token == "legacy-access-token"

    # The old global provider uniqueness must be gone.
    now = datetime.now(timezone.utc)
    run(
        "INSERT INTO workspaces (id, name, slug, created_at) VALUES (%s, %s, %s, %s)",
        (SECOND_WORKSPACE_ID, "Second Workspace", "second", now),
    )
    run(
        """
        INSERT INTO platform_connections (
            id, workspace_id, provider, status, metadata_json, created_at, updated_at
        ) VALUES (%s, %s, 'tiktok', 'disconnected', '{}'::json, %s, %s)
        """,
        (str(uuid4()), SECOND_WORKSPACE_ID, now, now),
    )

    duplicate_blocked = False
    try:
        run(
            """
            INSERT INTO platform_connections (
                id, workspace_id, provider, status, metadata_json, created_at, updated_at
            ) VALUES (%s, %s, 'tiktok', 'disconnected', '{}'::json, %s, %s)
            """,
            (str(uuid4()), LEGACY_WORKSPACE_ID, now, now),
        )
    except psycopg.errors.UniqueViolation:
        duplicate_blocked = True

    assert duplicate_blocked, "Expected per-workspace provider uniqueness constraint"

    revision = scalar("SELECT version_num FROM alembic_version")
    assert revision == "20261112_01", revision


if __name__ == "__main__":
    reset_legacy_schema()
    migrate()
    verify()
    print("Postgres legacy migration verification passed.")
