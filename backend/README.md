# Headline Avenue backend

This folder is the first source-first backend foundation for the Headline Avenue product.

## What exists now

- FastAPI application
- SQLAlchemy data model
- SQLite by default, with `DATABASE_URL` ready for PostgreSQL
- CORS for local development and the GitHub Pages frontend
- source ingestion records
- stories linked to sources
- evidence records for SourceGuard
- Story Pack output records
- a deterministic SourceGuard placeholder that does **not** pretend to perform semantic fact verification

## Run locally

```bash
cd backend
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open:

- API: http://127.0.0.1:8000
- Swagger docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## First workflow

1. POST `/api/v1/sources`
2. POST `/api/v1/stories`
3. POST `/api/v1/stories/{story_id}/evidence`
4. POST `/api/v1/sourceguard/check`
5. POST `/api/v1/story-packs/generate`

## Important

The current public dashboard remains a prototype. This backend does not yet publish to social platforms, download media, transcribe audio/video, or call an LLM. Those integrations should be added behind service interfaces after the core data model is stable.
