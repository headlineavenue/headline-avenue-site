from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import PlatformConnection


router = APIRouter(prefix="/oauth/tiktok", tags=["oauth", "tiktok"])
settings = get_settings()

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
REVOKE_URL = "https://open.tiktokapis.com/v2/oauth/revoke/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
STATE_COOKIE = "ha_tiktok_oauth_state"


def _configured() -> bool:
    return bool(
        settings.tiktok_client_key.strip()
        and settings.tiktok_client_secret.strip()
        and settings.tiktok_redirect_uri.strip()
    )


def _scope_list(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _connection(db: Session) -> PlatformConnection | None:
    return (
        db.query(PlatformConnection)
        .filter(PlatformConnection.provider == "tiktok")
        .first()
    )


def _status_payload(db: Session) -> dict:
    connection = _connection(db)
    scopes = _scope_list(connection.scope if connection else "")
    connected = bool(connection and connection.status == "connected" and connection.access_token)
    return {
        "provider": "tiktok",
        "configured": _configured(),
        "connected": connected,
        "status": connection.status if connection else "not_connected",
        "display_name": connection.display_name if connection else None,
        "avatar_url": connection.avatar_url if connection else None,
        "account_id": connection.account_id if connection else None,
        "scopes": scopes,
        "can_publish": connected and "video.publish" in scopes,
        "expires_at": connection.access_expires_at if connection else None,
        "refresh_expires_at": connection.refresh_expires_at if connection else None,
        "redirect_uri": settings.tiktok_redirect_uri or None,
    }


def _callback_page(status: str, message: str, profile: dict | None = None) -> HTMLResponse:
    payload = json.dumps(
        {
            "type": "ha:tiktok-oauth",
            "status": status,
            "message": message,
            "profile": profile or {},
        }
    ).replace("</", "<\\/")
    origin = json.dumps(settings.frontend_origin).replace("</", "<\\/")
    title = "TikTok connected" if status == "connected" else "TikTok authorization"
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#050b13;color:#eaf7ff;font-family:Inter,system-ui,sans-serif}}main{{width:min(420px,90vw);padding:26px;border:1px solid rgba(78,233,255,.18);border-radius:16px;background:#091625;text-align:center}}b{{display:block;font-size:20px;margin-bottom:8px}}p{{color:#8ca5b7;font-size:13px;line-height:1.5}}</style></head>
<body><main><b>{title}</b><p>{message}</p><p>You can close this window if it does not close automatically.</p></main>
<script>
const payload = {payload};
try {{ if (window.opener) window.opener.postMessage(payload, {origin}); }} catch (error) {{ console.error(error); }}
setTimeout(() => window.close(), 450);
</script></body></html>"""
    )


@router.get("/status")
def tiktok_status(db: Session = Depends(get_db)) -> dict:
    return _status_payload(db)


@router.get("/start")
def tiktok_start() -> RedirectResponse:
    if not _configured():
        raise HTTPException(
            status_code=503,
            detail="TikTok OAuth is not configured on the backend. Set TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, and TIKTOK_REDIRECT_URI.",
        )

    state = secrets.token_urlsafe(32)
    params = {
        "client_key": settings.tiktok_client_key,
        "scope": settings.tiktok_scopes,
        "response_type": "code",
        "redirect_uri": settings.tiktok_redirect_uri,
        "state": state,
    }
    response = RedirectResponse(f"{AUTHORIZE_URL}?{urlencode(params)}", status_code=302)
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=settings.tiktok_redirect_uri.startswith("https://"),
        samesite="lax",
    )
    return response


@router.get("/callback")
async def tiktok_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    stored_state = request.cookies.get(STATE_COOKIE)
    if error:
        response = _callback_page("error", error_description or error)
        response.delete_cookie(STATE_COOKIE)
        return response

    if not code or not state or not stored_state or not secrets.compare_digest(state, stored_state):
        response = _callback_page("error", "The TikTok authorization state could not be verified. Please try again.")
        response.delete_cookie(STATE_COOKIE)
        return response

    if not _configured():
        response = _callback_page("error", "TikTok OAuth configuration is incomplete on the Headline Avenue backend.")
        response.delete_cookie(STATE_COOKIE)
        return response

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_response = await client.post(
                TOKEN_URL,
                data={
                    "client_key": settings.tiktok_client_key,
                    "client_secret": settings.tiktok_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.tiktok_redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
            )
            token_data = token_response.json()
            if token_response.is_error or not token_data.get("access_token"):
                detail = token_data.get("error_description") or token_data.get("error") or "TikTok token exchange failed"
                response = _callback_page("error", str(detail))
                response.delete_cookie(STATE_COOKIE)
                return response

            access_token = str(token_data["access_token"])
            granted_scope = str(token_data.get("scope") or "")
            profile: dict = {}
            if "user.info.basic" in _scope_list(granted_scope):
                user_response = await client.get(
                    USER_INFO_URL,
                    params={"fields": "open_id,union_id,avatar_url,display_name"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if user_response.is_success:
                    body = user_response.json()
                    profile = dict((body.get("data") or {}).get("user") or {})

        now = datetime.now(timezone.utc)
        connection = _connection(db) or PlatformConnection(provider="tiktok")
        connection.status = "connected"
        connection.account_id = str(token_data.get("open_id") or profile.get("open_id") or "") or None
        connection.display_name = str(profile.get("display_name") or "") or None
        connection.avatar_url = str(profile.get("avatar_url") or "") or None
        connection.scope = granted_scope
        connection.access_token = access_token
        connection.refresh_token = str(token_data.get("refresh_token") or "") or None
        connection.access_expires_at = now + timedelta(seconds=int(token_data.get("expires_in") or 0))
        connection.refresh_expires_at = now + timedelta(seconds=int(token_data.get("refresh_expires_in") or 0))
        connection.metadata_json = {
            "union_id": profile.get("union_id"),
            "token_type": token_data.get("token_type"),
        }
        connection.updated_at = now
        db.add(connection)
        db.commit()
        db.refresh(connection)

        response = _callback_page(
            "connected",
            "TikTok authorized successfully. Headline Avenue stored the authorization on the backend.",
            {
                "display_name": connection.display_name,
                "avatar_url": connection.avatar_url,
                "scopes": _scope_list(connection.scope),
            },
        )
        response.delete_cookie(STATE_COOKIE)
        return response
    except httpx.HTTPError as exc:
        response = _callback_page("error", f"TikTok could not be reached: {exc}")
        response.delete_cookie(STATE_COOKIE)
        return response


@router.post("/refresh")
async def tiktok_refresh(db: Session = Depends(get_db)) -> dict:
    if not _configured():
        raise HTTPException(status_code=503, detail="TikTok OAuth is not configured")
    connection = _connection(db)
    if not connection or not connection.refresh_token:
        raise HTTPException(status_code=409, detail="TikTok is not connected")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_key": settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": connection.refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
        )
    data = response.json()
    if response.is_error or not data.get("access_token"):
        raise HTTPException(status_code=502, detail=data.get("error_description") or data.get("error") or "TikTok refresh failed")

    now = datetime.now(timezone.utc)
    connection.access_token = str(data["access_token"])
    connection.refresh_token = str(data.get("refresh_token") or connection.refresh_token)
    connection.scope = str(data.get("scope") or connection.scope or "")
    connection.access_expires_at = now + timedelta(seconds=int(data.get("expires_in") or 0))
    connection.refresh_expires_at = now + timedelta(seconds=int(data.get("refresh_expires_in") or 0))
    connection.updated_at = now
    db.commit()
    return _status_payload(db)


@router.post("/disconnect")
async def tiktok_disconnect(db: Session = Depends(get_db)) -> dict:
    connection = _connection(db)
    if not connection:
        return _status_payload(db)

    if _configured() and connection.access_token:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                REVOKE_URL,
                data={
                    "client_key": settings.tiktok_client_key,
                    "client_secret": settings.tiktok_client_secret,
                    "token": connection.access_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
            )
        if response.is_error:
            try:
                detail = response.json().get("error_description") or response.json().get("error")
            except Exception:
                detail = response.text
            raise HTTPException(status_code=502, detail=detail or "TikTok revoke failed")

    connection.status = "disconnected"
    connection.access_token = None
    connection.refresh_token = None
    connection.access_expires_at = None
    connection.refresh_expires_at = None
    connection.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _status_payload(db)
