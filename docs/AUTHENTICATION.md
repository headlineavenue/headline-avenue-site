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
