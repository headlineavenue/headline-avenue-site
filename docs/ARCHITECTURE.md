# Headline Avenue product architecture v1

## Product principle

**Source-first, not video-first.**

A YouTube interview, uploaded video, podcast, article, PDF, transcript, press release, or other supported input becomes a **Source**. Sources contain evidence. Evidence can support one or more **Stories**. Stories can generate many **Outputs**. Outputs can be sent through **Publishing Jobs**. Performance data later feeds back into Radar and Story Intelligence.

## Core domain

```text
Workspace
  ├── Sources
  │     └── Stories
  │           ├── Evidence
  │           └── Story Outputs
  │                  └── Publishing Jobs
  └── Watchlists / Radar signals  (next)
```

### Workspace

Tenant boundary for a creator, newsroom, brand, or team.

### Source

Normalized source material.

Examples:
- URL
- video
- audio
- article
- PDF
- transcript

Future ingestion pipeline:

```text
raw input
  → fetch/upload
  → metadata extraction
  → text/transcript extraction
  → segmentation + timestamps
  → entities / claims / moments
  → indexed Source
```

### Story

Editorial interpretation of a source. A source may contain several valid stories.

A Story stores:
- title
- editorial angle
- signal score
- status
- source relationship

### Evidence

The traceable support layer behind SourceGuard.

Evidence should eventually store:
- exact excerpt
- source ID
- time or page position
- claim being evaluated
- support classification
- model/tool provenance
- reviewer decision

### Story Output

A format-specific deliverable generated from a Story.

Examples:
- 9:16 video
- 16:9 video
- article
- carousel
- newsletter
- thread
- platform copy
- headline variants

### Publishing Job

A controlled attempt to distribute an output to an authorized destination.

Future fields should include:
- destination account
- scheduled time
- attempt history
- external post ID
- platform error
- retry policy
- approval/reviewer state

## Service boundaries

The backend should evolve into these services without forcing them into separate deploys yet:

1. **Ingestion service** — fetches/uploads source material.
2. **Transcription/extraction service** — converts source media/documents into structured text.
3. **Story intelligence service** — proposes and ranks editorial angles.
4. **SourceGuard service** — maps claims to supporting evidence and flags unsupported changes.
5. **Generation service** — creates Story Pack outputs.
6. **Publishing service** — connects authorized social accounts and publishes/schedules outputs.
7. **Analytics service** — imports performance and computes normalized signals.
8. **Radar service** — watchlists, trend velocity, and opportunity ranking.

## API direction

Current foundation:

- `GET /health`
- `POST /api/v1/sources`
- `GET /api/v1/sources`
- `GET /api/v1/sources/{id}`
- `POST /api/v1/stories`
- `GET /api/v1/stories`
- `GET /api/v1/stories/{id}`
- `POST /api/v1/stories/{id}/evidence`
- `GET /api/v1/stories/{id}/evidence`
- `POST /api/v1/sourceguard/check`
- `POST /api/v1/story-packs/generate`

## Persistence

Development starts on SQLite for zero-friction local work. The schema is intentionally PostgreSQL-compatible through SQLAlchemy. Before production:

- switch `DATABASE_URL` to PostgreSQL
- add Alembic migrations
- use object storage for media
- encrypt OAuth credentials/tokens
- move long-running ingestion/generation to a queue

## Security principles

- Never store third-party passwords.
- OAuth tokens must be encrypted at rest before production.
- Workspace boundaries must be enforced server-side.
- Do not let a client choose arbitrary workspace IDs after authentication exists.
- SourceGuard evidence and reviewer actions should be auditable.
- Publishing must require authorized destination accounts and clear user intent.
- Public-source ingestion must respect provider terms and applicable rights.

## Next milestone

Connect the static product UI to the backend locally for **Sources → Story Workspace → Story Pack** using real persisted records, while preserving the current polished visual design.
