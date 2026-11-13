# Headline Avenue

Headline Avenue is a source-first editorial intelligence and publishing workspace for fast-moving media.

## Current architecture

```text
Browser app
  → authenticated workspace
    → Source
      → Story
        → Evidence / SourceGuard
          → Story Pack outputs
            → Publishing jobs
```

Public infrastructure:

- marketing/product frontend: GitHub Pages today; planned apex domain `https://headlineavenue.com`
- permanent API domain: `https://api.headlineavenue.com`
- backend: Railway / FastAPI
- database: Railway PostgreSQL
- TikTok: Login Kit sandbox connected; Production review pending

See `docs/ARCHITECTURE.md` and `docs/AUTHENTICATION.md`.

## Public pages

- `index.html` — marketing site
- `app.html` — product application
- `privacy.html` — privacy policy
- `terms.html` — terms of service
- `data-deletion.html` — data deletion instructions
- `contact.html` — contact information

## Backend

The backend lives in `backend/` and currently includes:

- FastAPI
- SQLAlchemy 2
- PostgreSQL in hosted production
- SQLite for local development
- Alembic migrations
- server-side user sessions and workspace memberships on the auth feature branch
- Sources, Stories and Evidence
- source-grounded editorial intelligence
- SourceGuard gates and editor approval
- Story Pack records
- controlled publishing preflight/jobs
- TikTok OAuth with workspace-scoped provider connections on the auth feature branch

## Run locally

The local browser uses the local API automatically.

First update dependencies:

```powershell
cd $HOME\Documents\headline-avenue-site\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then launch from the repository root:

```powershell
cd $HOME\Documents\headline-avenue-site
powershell -ExecutionPolicy Bypass -File .\start-headline-avenue.ps1
```

This opens:

- frontend: `http://localhost:5500/app.html`
- backend: `http://127.0.0.1:8000`

A Cloudflare quick tunnel is no longer required for ordinary development. Use the optional tunnel only for a provider flow that specifically needs a public callback:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-headline-avenue.ps1 -WithTunnel
```

## Real workflow today

```text
Create Source
  → create Story
  → analyze indexed source text
  → generate/select editorial headline
  → SourceGuard / editor gate
  → generate Story Pack records
  → create Publish draft
  → run preflight
  → create controlled backend publishing jobs
```

The hosted public application already talks to the permanent backend. Some product areas such as Radar, Analytics and actual media rendering still contain prototype layers and should not be presented as fully implemented.

## Next product milestone

After the authentication/workspace branch is validated and deployed safely:

1. real binary media upload/object storage
2. asynchronous transcription/extraction with timestamps
3. real Story Pack content generation
4. TikTok Content Posting adapter behind an approval/feature gate
5. first pilot users

## Current media limitation

URL, article and pasted-transcript sources can persist and be analyzed. Video/audio/PDF selections can create source metadata, but binary media storage, transcription and rendering are the next implementation layer.
