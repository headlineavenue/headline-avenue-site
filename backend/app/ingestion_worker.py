from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal, engine
from .models import AuditLog, IngestionJob, Source, SourceTranscriptSegment
from .services.transcription import transcribe_media


settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _claim_next_job(db: Session) -> IngestionJob | None:
    stmt = (
        select(IngestionJob)
        .where(IngestionJob.status == "queued")
        .order_by(IngestionJob.created_at.asc(), IngestionJob.id.asc())
    )
    if engine.dialect.name != "sqlite":
        stmt = stmt.with_for_update(skip_locked=True)

    job = db.scalar(stmt)
    if not job:
        return None

    job.status = "processing"
    job.attempts += 1
    job.started_at = _now()
    job.error_message = None

    source = db.get(Source, job.source_id)
    if source:
        source.status = "transcribing"

    db.commit()
    db.refresh(job)
    return job


def _recover_stale_jobs(db: Session) -> int:
    cutoff = _now() - timedelta(minutes=30)
    jobs = list(
        db.scalars(
            select(IngestionJob).where(
                IngestionJob.status == "processing",
                IngestionJob.started_at.is_not(None),
                IngestionJob.started_at < cutoff,
            )
        )
    )
    for job in jobs:
        job.status = "queued"
        job.error_message = "Recovered after stale worker lease"
        source = db.get(Source, job.source_id)
        if source and source.status == "transcribing":
            source.status = "transcription_queued"
    if jobs:
        db.commit()
    return len(jobs)


def _complete_job(job_id: str, result) -> None:
    db = SessionLocal()
    try:
        job = db.get(IngestionJob, job_id)
        if not job:
            return
        source = db.get(Source, job.source_id)
        if not source:
            raise RuntimeError("Source disappeared during transcription")

        db.execute(
            delete(SourceTranscriptSegment).where(
                SourceTranscriptSegment.source_id == source.id
            )
        )
        for segment in result.segments:
            db.add(
                SourceTranscriptSegment(
                    source_id=source.id,
                    sequence=segment.sequence,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    speaker=segment.speaker,
                    text=segment.text,
                    confidence=segment.confidence,
                )
            )

        metadata = dict(source.metadata_json or {})
        metadata["transcription"] = {
            "provider": result.provider,
            "model": result.model,
            "request_id": result.request_id,
            "language": result.language,
            "duration_seconds": result.duration_seconds,
            "segment_count": len(result.segments),
            "completed_at": _now().isoformat(),
        }

        source.transcript_text = result.text
        source.metadata_json = metadata
        source.status = "indexed"

        job.status = "completed"
        job.completed_at = _now()
        job.error_message = None

        db.add(
            AuditLog(
                workspace_id=job.workspace_id,
                user_id=None,
                action="source.transcription_completed",
                entity_type="source",
                entity_id=source.id,
                details_json={
                    "provider": result.provider,
                    "model": result.model,
                    "segment_count": len(result.segments),
                    "language": result.language,
                },
            )
        )
        db.commit()
    finally:
        db.close()


def _fail_job(job_id: str, exc: Exception) -> None:
    db = SessionLocal()
    try:
        job = db.get(IngestionJob, job_id)
        if not job:
            return
        source = db.get(Source, job.source_id)
        message = str(exc)[:2000]

        job.status = "failed"
        job.completed_at = _now()
        job.error_message = message
        if source:
            source.status = "transcription_failed"

        db.add(
            AuditLog(
                workspace_id=job.workspace_id,
                user_id=None,
                action="source.transcription_failed",
                entity_type="source",
                entity_id=job.source_id,
                details_json={
                    "provider": job.provider,
                    "error": message,
                },
            )
        )
        db.commit()
    finally:
        db.close()


def process_one() -> bool:
    db = SessionLocal()
    try:
        _recover_stale_jobs(db)
        job = _claim_next_job(db)
        if not job:
            return False
        source = db.get(Source, job.source_id)
        if not source:
            raise RuntimeError("Queued transcription source was not found")
        media = dict((source.metadata_json or {}).get("media") or {})
        job_id = job.id
    except Exception:
        db.close()
        raise
    finally:
        if db.is_active:
            db.close()

    try:
        result = transcribe_media(media)
        _complete_job(job_id, result)
    except Exception as exc:
        _fail_job(job_id, exc)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Headline Avenue ingestion worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one queued job and exit",
    )
    args = parser.parse_args()

    print("Headline Avenue ingestion worker started.")
    while True:
        processed = process_one()
        if args.once:
            break
        if not processed:
            time.sleep(max(0.5, settings.ingestion_worker_poll_seconds))


if __name__ == "__main__":
    main()
