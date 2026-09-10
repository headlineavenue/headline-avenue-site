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
- deterministic source intelligence for pasted transcripts and readable public web pages
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
3. POST `/api/v1/stories/{story_id}/analyze`
4. POST `/api/v1/stories/{story_id}/evidence`
5. POST `/api/v1/sourceguard/check`
6. POST `/api/v1/story-packs/generate`

## Source intelligence v1

`POST /api/v1/stories/{story_id}/analyze` now performs real source-grounded processing without an LLM:

- uses pasted transcript/source text directly, or
- fetches readable HTML/text from a public article/web URL
- normalizes and stores the extracted text
- ranks up to three sentence-level story opportunities
- creates direct-extract evidence records
- updates the Story's top angle and signal score
- returns a SourceGuard trace that clearly labels the verification level as `direct_extract`

This is intentionally conservative. It does not invent timestamps, quotes, facts, or semantic verification. YouTube transcript extraction, binary upload processing, and LLM editorial generation are separate later layers.

## Important

The current public dashboard remains a prototype. The local frontend already persists Sources, Stories, and Story Pack records. Source intelligence is now available through the API; the next frontend milestone is replacing the workspace's prototype angle cards with the real `/analyze` response.
