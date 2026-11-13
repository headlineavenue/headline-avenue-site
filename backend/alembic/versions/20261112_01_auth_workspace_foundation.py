"""Add authentication, workspace memberships, audit logs, and tenant platform connections.

Revision ID: 20261112_01
Revises:
Create Date: 2026-11-12
"""

from __future__ import annotations

from uuid import uuid4
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261112_01"
down_revision = None
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(bind).get_columns(table)}


def _index_info(bind, table: str) -> list[dict]:
    return list(sa.inspect(bind).get_indexes(table))


def _unique_info(bind, table: str) -> list[dict]:
    return list(sa.inspect(bind).get_unique_constraints(table))


def _ensure_auth_tables(bind) -> None:
    tables = _tables(bind)

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("display_name", sa.String(160), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    tables = _tables(bind)
    if "workspace_memberships" not in tables:
        op.create_table(
            "workspace_memberships",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(40), nullable=False, server_default="member"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_membership"),
        )
        op.create_index("ix_workspace_memberships_workspace_id", "workspace_memberships", ["workspace_id"])
        op.create_index("ix_workspace_memberships_user_id", "workspace_memberships", ["user_id"])
        op.create_index("ix_workspace_memberships_role", "workspace_memberships", ["role"])

    tables = _tables(bind)
    if "user_sessions" not in tables:
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("csrf_hash", sa.String(64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
        )
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
        op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)
        op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    tables = _tables(bind)
    if "audit_logs" not in tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("action", sa.String(120), nullable=False),
            sa.Column("entity_type", sa.String(80), nullable=True),
            sa.Column("entity_id", sa.String(255), nullable=True),
            sa.Column("details_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_audit_logs_workspace_id", "audit_logs", ["workspace_id"])
        op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
        op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def _ensure_platform_tenancy(bind) -> None:
    if "platform_connections" not in _tables(bind):
        return

    existing_columns = _columns(bind, "platform_connections")
    if "workspace_id" in existing_columns:
        return

    op.add_column(
        "platform_connections",
        sa.Column("workspace_id", sa.String(36), nullable=True),
    )

    workspace_id = bind.execute(
        sa.text("SELECT id FROM workspaces ORDER BY created_at ASC LIMIT 1")
    ).scalar()

    if not workspace_id:
        workspace_id = str(uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO workspaces (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, :created_at)"
            ),
            {
                "id": workspace_id,
                "name": "Legacy Workspace",
                "slug": f"legacy-{str(uuid4())[:8]}",
                "created_at": datetime.now(timezone.utc),
            },
        )

    bind.execute(
        sa.text(
            "UPDATE platform_connections SET workspace_id = :workspace_id "
            "WHERE workspace_id IS NULL"
        ),
        {"workspace_id": workspace_id},
    )

    indexes = _index_info(bind, "platform_connections")
    unique_constraints = _unique_info(bind, "platform_connections")

    for index in indexes:
        if index.get("unique") and index.get("column_names") == ["provider"]:
            op.drop_index(index["name"], table_name="platform_connections")

    for constraint in unique_constraints:
        if constraint.get("column_names") == ["provider"] and constraint.get("name"):
            op.drop_constraint(
                constraint["name"],
                "platform_connections",
                type_="unique",
            )

    dialect = bind.dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("platform_connections") as batch:
            batch.alter_column(
                "workspace_id",
                existing_type=sa.String(36),
                nullable=False,
            )
            batch.create_unique_constraint(
                "uq_platform_connection_workspace_provider",
                ["workspace_id", "provider"],
            )
    else:
        op.alter_column(
            "platform_connections",
            "workspace_id",
            existing_type=sa.String(36),
            nullable=False,
        )
        op.create_foreign_key(
            "fk_platform_connections_workspace_id",
            "platform_connections",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_unique_constraint(
            "uq_platform_connection_workspace_provider",
            "platform_connections",
            ["workspace_id", "provider"],
        )

    refreshed_indexes = _index_info(bind, "platform_connections")
    index_names = {item.get("name") for item in refreshed_indexes}
    provider_indexes = [
        item for item in refreshed_indexes if item.get("column_names") == ["provider"]
    ]
    if not provider_indexes:
        op.create_index(
            "ix_platform_connections_provider",
            "platform_connections",
            ["provider"],
            unique=False,
        )
    if "ix_platform_connections_workspace_id" not in index_names:
        op.create_index(
            "ix_platform_connections_workspace_id",
            "platform_connections",
            ["workspace_id"],
            unique=False,
        )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_auth_tables(bind)
    _ensure_platform_tenancy(bind)


def downgrade() -> None:
    bind = op.get_bind()

    if "platform_connections" in _tables(bind) and "workspace_id" in _columns(bind, "platform_connections"):
        indexes = _index_info(bind, "platform_connections")
        for index in indexes:
            if index.get("column_names") == ["workspace_id"] and index.get("name"):
                op.drop_index(index["name"], table_name="platform_connections")

        constraints = _unique_info(bind, "platform_connections")
        for constraint in constraints:
            if (
                constraint.get("column_names") == ["workspace_id", "provider"]
                and constraint.get("name")
            ):
                op.drop_constraint(
                    constraint["name"],
                    "platform_connections",
                    type_="unique",
                )

        if bind.dialect.name != "sqlite":
            foreign_keys = sa.inspect(bind).get_foreign_keys("platform_connections")
            for fk in foreign_keys:
                if fk.get("constrained_columns") == ["workspace_id"] and fk.get("name"):
                    op.drop_constraint(
                        fk["name"],
                        "platform_connections",
                        type_="foreignkey",
                    )

        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("platform_connections") as batch:
                batch.drop_column("workspace_id")
        else:
            op.drop_column("platform_connections", "workspace_id")

        provider_indexes = _index_info(bind, "platform_connections")
        for index in provider_indexes:
            if index.get("column_names") == ["provider"] and index.get("name"):
                op.drop_index(index["name"], table_name="platform_connections")
        op.create_index(
            "ix_platform_connections_provider",
            "platform_connections",
            ["provider"],
            unique=True,
        )

    for table in ("audit_logs", "user_sessions", "workspace_memberships", "users"):
        if table in _tables(bind):
            op.drop_table(table)
