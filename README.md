# Headline Avenue

Headline Avenue is a source-first editorial intelligence and publishing workspace for fast-moving media.

The public GitHub Pages site contains the marketing site and polished product demo. The repository now also contains the first real backend foundation for the product.

## Public pages

- `index.html` — marketing site
- `app.html` — product demo
- `privacy.html` — privacy policy
- `terms.html` — terms of service
- `data-deletion.html` — data deletion instructions
- `contact.html` — contact information

## Product architecture

Headline Avenue follows a source-first model:

```text
Source
  → Story
    → Evidence / SourceGuard
    → Story Pack outputs
      → Publishing jobs
        → Analytics
          → Radar intelligence
```

See `docs/ARCHITECTURE.md` for the full architecture.

## Frontend

Static HTML, CSS, and JavaScript, designed for GitHub Pages with no build step.

Expected public site:

`https://headlineavenue.github.io/headline-avenue-site/`

## Backend

The first API foundation lives in `backend/`.

Current stack:

- FastAPI
- SQLAlchemy 2
- Pydantic
- SQLite for zero-friction development
- PostgreSQL-ready through `DATABASE_URL`

Current API foundations cover:

- workspaces
- sources
- stories
- evidence
- SourceGuard checks
- Story Pack output records
- publishing-job data model

### Run locally

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Then open:

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## Development principle

The current product demo must remain visually polished while backend functionality is introduced incrementally. Real data should replace prototype data one workflow at a time rather than rewriting the whole interface at once.
