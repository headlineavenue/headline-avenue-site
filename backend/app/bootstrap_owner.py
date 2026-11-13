from __future__ import annotations

from datetime import datetime, timezone

from pwdlib import PasswordHash
from sqlalchemy import func, select

from .config import get_settings
from .database import SessionLocal
from .models import AuditLog, User, Workspace, WorkspaceMembership


settings = get_settings()
password_hash = PasswordHash.recommended()


def _normalized_email(value: str) -> str:
    return value.strip().lower()


def main() -> None:
    email = _normalized_email(settings.auth_bootstrap_owner_email)
    password = settings.auth_bootstrap_owner_password
    display_name = settings.auth_bootstrap_owner_name.strip() or "Headline Avenue Owner"

    # No bootstrap credentials means normal startup; this script is safe to
    # leave in the Docker command after the first deployment.
    if not email and not password:
        print("Owner bootstrap not configured; skipping.")
        return

    if not email or not password:
        raise RuntimeError(
            "Both AUTH_BOOTSTRAP_OWNER_EMAIL and AUTH_BOOTSTRAP_OWNER_PASSWORD "
            "must be set together"
        )
    if len(password) < 12:
        raise RuntimeError("Bootstrap owner password must be at least 12 characters")

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        created_user = False
        if not user:
            user = User(
                email=email,
                password_hash=password_hash.hash(password),
                display_name=display_name,
                is_active=True,
            )
            db.add(user)
            db.flush()
            created_user = True

        existing_membership = db.scalar(
            select(WorkspaceMembership)
            .where(WorkspaceMembership.user_id == user.id)
            .order_by(WorkspaceMembership.created_at.asc())
        )
        if existing_membership:
            print(
                "Bootstrap owner already has workspace access; "
                "no membership change required."
            )
            if created_user:
                db.commit()
            return

        # Prefer an existing legacy workspace with no members so current
        # Sources/Stories/provider connections remain accessible after auth is
        # introduced. If none exists, use the oldest workspace.
        membership_count = (
            select(
                Workspace.id.label("workspace_id"),
                func.count(WorkspaceMembership.id).label("member_count"),
            )
            .outerjoin(
                WorkspaceMembership,
                WorkspaceMembership.workspace_id == Workspace.id,
            )
            .group_by(Workspace.id)
            .subquery()
        )
        workspace = db.scalar(
            select(Workspace)
            .join(
                membership_count,
                membership_count.c.workspace_id == Workspace.id,
            )
            .where(membership_count.c.member_count == 0)
            .order_by(Workspace.created_at.asc(), Workspace.id.asc())
        )
        if not workspace:
            workspace = db.scalar(
                select(Workspace).order_by(Workspace.created_at.asc(), Workspace.id.asc())
            )
        if not workspace:
            raise RuntimeError("No workspace exists for bootstrap owner assignment")

        membership = WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
        )
        db.add(membership)
        db.flush()
        db.add(
            AuditLog(
                workspace_id=workspace.id,
                user_id=user.id,
                action="auth.bootstrap_owner",
                entity_type="workspace_membership",
                entity_id=membership.id,
                details_json={"legacy_workspace_claimed": True},
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        print(
            f"Bootstrap owner ready for workspace '{workspace.slug}'. "
            "Remove bootstrap password from hosted environment after verifying login."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
