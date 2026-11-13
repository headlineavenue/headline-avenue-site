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

The current public application is served from `headlineavenue.github.io` while the API is served from `*.up.railway.app`.

That is cross-site browser authentication. The feature branch deliberately uses secure HttpOnly cookies, which are safer than storing bearer credentials in JavaScript, but cross-site cookies can be restricted by browser privacy controls.

Do not merge/deploy this authentication branch until one of these is proven:

1. the target browsers reliably retain/send the session cookie with `credentials: include`, or
2. the production frontend and API are moved under the same registrable custom domain (preferred), for example `app.example.com` and `api.example.com`.

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
