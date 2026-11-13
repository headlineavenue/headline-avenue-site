from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import APIKeyCookie
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import User, UserSession, Workspace, WorkspaceMembership


settings = get_settings()
session_cookie = APIKeyCookie(
    name=settings.auth_cookie_name,
    scheme_name="HeadlineAvenueSession",
    auto_error=False,
)


def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession


@dataclass(frozen=True)
class WorkspaceContext:
    auth: AuthContext
    workspace: Workspace
    membership: WorkspaceMembership


def get_auth_context(
    raw_session: str | None = Depends(session_cookie),
    db: Session = Depends(get_db),
) -> AuthContext:
    if not raw_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == token_digest(raw_session))
    )
    if not session or session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or has been revoked",
        )

    if aware_utc(session.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired",
        )

    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is unavailable",
        )

    return AuthContext(user=user, session=session)


def require_csrf(request: Request, session: UserSession) -> None:
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not secrets.compare_digest(token_digest(supplied), session.csrf_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token is missing or invalid",
        )


def require_workspace(
    workspace_id: str,
    auth: AuthContext,
    db: Session,
    roles: set[str] | None = None,
) -> tuple[Workspace, WorkspaceMembership]:
    membership = db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == auth.user.id,
        )
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if roles and membership.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace role does not allow this action",
        )

    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace, membership


def get_workspace_context(
    request: Request,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-ID"),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WorkspaceContext:
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Workspace-ID header is required",
        )
    workspace, membership = require_workspace(workspace_id, auth, db)
    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        require_csrf(request, auth.session)
    return WorkspaceContext(auth=auth, workspace=workspace, membership=membership)
