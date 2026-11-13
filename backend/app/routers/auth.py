from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import AuditLog, User, UserSession, Workspace, WorkspaceMembership
from ..security import (
    AuthContext,
    csrf_token_for_session,
    get_auth_context,
    require_csrf,
    token_digest,
)


router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash("headline-avenue-dummy-password-not-a-user")


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    display_name: str = Field(min_length=2, max_length=160)
    workspace_name: str | None = Field(default=None, min_length=2, max_length=160)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str


class WorkspaceMembershipOut(BaseModel):
    workspace_id: str
    workspace_name: str
    workspace_slug: str
    role: str


class AuthSessionOut(BaseModel):
    user: UserOut
    workspaces: list[WorkspaceMembershipOut]
    active_workspace_id: str
    csrf_token: str


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _slug_base(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return (slug or "workspace")[:90]


def _new_workspace_slug(db: Session, name: str) -> str:
    base = _slug_base(name)
    for _ in range(10):
        candidate = f"{base}-{secrets.token_hex(3)}"
        if not db.scalar(select(Workspace.id).where(Workspace.slug == candidate)):
            return candidate
    raise HTTPException(status_code=503, detail="Could not allocate workspace slug")


def _memberships(db: Session, user_id: str) -> list[WorkspaceMembershipOut]:
    rows = db.execute(
        select(WorkspaceMembership, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .where(WorkspaceMembership.user_id == user_id)
        .order_by(WorkspaceMembership.created_at.asc())
    ).all()
    return [
        WorkspaceMembershipOut(
            workspace_id=membership.workspace_id,
            workspace_name=workspace.name,
            workspace_slug=workspace.slug,
            role=membership.role,
        )
        for membership, workspace in rows
    ]


def _issue_session(db: Session, user: User) -> tuple[str, str, UserSession]:
    session_token = secrets.token_urlsafe(48)
    session_hash = token_digest(session_token)
    now = datetime.now(timezone.utc)
    session = UserSession(
        user_id=user.id,
        token_hash=session_hash,
        csrf_hash="pending",
        expires_at=now + timedelta(days=settings.auth_session_days),
        last_seen_at=now,
    )
    csrf_token = csrf_token_for_session(session)
    session.csrf_hash = token_digest(csrf_token)
    db.add(session)
    db.flush()
    return session_token, csrf_token, session


def _set_session_cookie(response: Response, session_token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=session_token,
        max_age=settings.auth_session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )


def _session_payload(db: Session, user: User, csrf_token: str) -> AuthSessionOut:
    memberships = _memberships(db, user.id)
    if not memberships:
        raise HTTPException(status_code=409, detail="User has no workspace membership")
    return AuthSessionOut(
        user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
        workspaces=memberships,
        active_workspace_id=memberships[0].workspace_id,
        csrf_token=csrf_token,
    )


@router.post("/register", response_model=AuthSessionOut, status_code=201)
def register(
    payload: RegisterIn,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthSessionOut:
    if not settings.auth_registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is not enabled",
        )

    email = _normalize_email(str(payload.email))
    existing = db.scalar(select(User.id).where(User.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    display_name = payload.display_name.strip()
    workspace_name = (payload.workspace_name or f"{display_name}'s Workspace").strip()

    user = User(
        email=email,
        password_hash=password_hash.hash(payload.password),
        display_name=display_name,
    )
    workspace = Workspace(
        name=workspace_name,
        slug=_new_workspace_slug(db, workspace_name),
    )
    db.add_all([user, workspace])
    db.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
    )
    db.add(membership)
    session_token, csrf_token, session = _issue_session(db, user)
    db.add(
        AuditLog(
            workspace_id=workspace.id,
            user_id=user.id,
            action="auth.register",
            entity_type="user",
            entity_id=user.id,
            details_json={"session_id": session.id},
        )
    )
    db.commit()

    _set_session_cookie(response, session_token)
    return _session_payload(db, user, csrf_token)


@router.post("/login", response_model=AuthSessionOut)
def login(
    payload: LoginIn,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthSessionOut:
    email = _normalize_email(str(payload.email))
    user = db.scalar(select(User).where(User.email == email))

    candidate_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    valid = password_hash.verify(payload.password, candidate_hash)
    if not user or not valid or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
        )

    session_token, csrf_token, session = _issue_session(db, user)
    memberships = _memberships(db, user.id)
    if not memberships:
        raise HTTPException(status_code=409, detail="User has no workspace membership")

    db.add(
        AuditLog(
            workspace_id=memberships[0].workspace_id,
            user_id=user.id,
            action="auth.login",
            entity_type="session",
            entity_id=session.id,
            details_json={},
        )
    )
    db.commit()

    _set_session_cookie(response, session_token)
    return _session_payload(db, user, csrf_token)


@router.get("/me", response_model=AuthSessionOut)
def me(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AuthSessionOut:
    csrf_token = csrf_token_for_session(auth.session)
    auth.session.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return _session_payload(db, auth.user, csrf_token)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    require_csrf(request, auth.session)
    auth.session.revoked_at = datetime.now(timezone.utc)

    memberships = _memberships(db, auth.user.id)
    if memberships:
        db.add(
            AuditLog(
                workspace_id=memberships[0].workspace_id,
                user_id=auth.user.id,
                action="auth.logout",
                entity_type="session",
                entity_id=auth.session.id,
                details_json={},
            )
        )
    db.commit()

    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
