# Headline Avenue authentication foundation

This branch introduces the security boundary required before real customer onboarding.

## Model

- Passwords are hashed with Argon2 through `pwdlib`.
- Browser sessions use opaque random tokens.
- Only a SHA-256 digest of the session token is stored in PostgreSQL.
- Sessions are revocable and expire server-side.
- Unsafe authenticated requests require a per-session CSRF token.
- Every product request carries `X-Workspace-ID`.
- The backend verifies membership instead of trusting a client-supplied workspace slug.
- Provider connections belong to a workspace.
- TikTok access and refresh tokens are encrypted at rest using Fernet.
- Privileged actions are role-gated and written to `audit_logs`.

## Roles

Current policy:

- `owner`: workspace administration, provider connect/disconnect, editorial approval, publishing.
- `editor`: editorial approval, publishing, token refresh.
- other future roles: no privileged provider/publishing administration until explicitly granted.

## Deployment blocker: site topology

The branded backend is now live at `https://api.headlineavenue.com`. The intended production frontend is `https://headlineavenue.com`, which places the browser app and API under the same registrable domain.

Until the frontend is moved from GitHub Pages to `headlineavenue.com`, the temporary topology remains cross-site. Do not deploy authenticated customer access on that temporary topology unless `AUTH_COOKIE_SAMESITE=none` is explicitly tested in target browsers.

Preferred production policy after the frontend move:

- `AUTH_COOKIE_SECURE=true`
- `AUTH_COOKIE_SAMESITE=lax`
- frontend: `https://headlineavenue.com`
- API: `https://api.headlineavenue.com`

## Migration rollout

Hosted startup performs:

1. `python -m app.bootstrap_db`
2. `alembic upgrade head`
3. Uvicorn startup

The bootstrap is transitional. It creates tables missing from a fresh database without mutating existing columns. Alembic then performs the structural migration that `create_all()` cannot perform, including backfilling the legacy TikTok connection to the existing workspace.

Before production deployment:

- back up Railway PostgreSQL,
- run the migration against a staging copy,
- verify the existing TikTok connection remains present,
- set `TOKEN_ENCRYPTION_KEY`,
- test register/login/logout and tenant isolation,
- only then deploy to production.


## Production first-owner bootstrap

The existing production database predates user accounts. Its current Sources, Stories and TikTok connection belong to the legacy workspace, so the first authenticated owner must be attached to that workspace instead of receiving a new empty workspace.

Before the first auth deployment, set these Railway variables:

```text
AUTH_REGISTRATION_ENABLED=false
AUTH_BOOTSTRAP_OWNER_EMAIL=<owner login email>
AUTH_BOOTSTRAP_OWNER_PASSWORD=<strong temporary bootstrap password, 12+ chars>
AUTH_BOOTSTRAP_OWNER_NAME=<owner display name>
TOKEN_ENCRYPTION_KEY=<Fernet key>
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
FRONTEND_ORIGIN=https://headlineavenue.com
CORS_ORIGINS=https://headlineavenue.com,https://www.headlineavenue.com
```

The hosted startup sequence is intentionally ordered:

1. create missing tables needed by the transitional baseline,
2. run Alembic,
3. encrypt any legacy provider tokens,
4. attach/create the bootstrap owner for the existing unowned workspace,
5. start Uvicorn.

The owner bootstrap is idempotent. Once login is verified and the owner can see the existing workspace data and TikTok connection, remove `AUTH_BOOTSTRAP_OWNER_PASSWORD` (and optionally the other bootstrap owner variables) from Railway. The password hash remains in PostgreSQL; the plaintext bootstrap password does not need to remain in the hosting environment.

Public registration remains closed in production by default. Do not enable it until email verification, abuse controls and the intended invitation/onboarding model exist.

## TikTok review constraint

While the TikTok Production app is still under review, keep its registered callback on the existing Railway hostname:

```text
https://headline-avenue-site-production.up.railway.app/api/v1/oauth/tiktok/callback
```

The branded API domain `https://api.headlineavenue.com` can coexist with that hostname. Do not change the TikTok callback merely because the branded API is live. Move the callback only after TikTok approval and a controlled production cutover.
