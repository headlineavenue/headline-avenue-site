from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import get_settings
from ..models import (
    AuditLog,
    IngestionJob,
    Source,
    SourceTranscriptSegment,
    Story,
)
from ..schemas import (
    IngestionJobOut,
    SourceCreate,
    SourceLibraryItemOut,
    SourceLibraryOut,
    SourceOut,
    SourceTranscriptOut,
    TranscriptSegmentOut,
)
from ..services.media_storage import store_upload
from ..security import WorkspaceContext, get_workspace_context

router = APIRouter(prefix="/sources", tags=["sources"])
settings = get_settings()


@router.post("", response_model=SourceOut, status_code=201)
def create_source(
    payload: SourceCreate,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> Source:
    source = Source(
        workspace_id=workspace.workspace.id,
        kind=payload.kind,
        title=payload.title,
        original_url=str(payload.original_url) if payload.original_url else None,
        transcript_text=payload.transcript_text,
        metadata_json=payload.metadata,
        status="indexed" if payload.transcript_text else "queued",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.post("/upload", response_model=SourceOut, status_code=201)
async def upload_source(
    kind: Annotated[Literal["video", "audio", "pdf"], Form()],
    file: Annotated[UploadFile, File()],
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> Source:
    content_type = (file.content_type or "").lower()
    if kind == "video" and not content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Expected a video upload")
    if kind == "audio" and not content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Expected an audio upload")
    if kind == "pdf" and content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Expected a PDF upload")

    source = Source(
        workspace_id=workspace.workspace.id,
        kind=kind,
        title=file.filename or f"{kind} upload",
        metadata_json={},
        status="uploading",
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    try:
        stored = await store_upload(
            file,
            workspace_id=workspace.workspace.id,
            source_id=source.id,
        )
    except ValueError as exc:
        db.delete(source)
        db.commit()
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except Exception as exc:
        source.status = "upload_failed"
        source.metadata_json = {"media": {"error": str(exc)}}
        db.add(
            AuditLog(
                workspace_id=workspace.workspace.id,
                user_id=workspace.auth.user.id,
                action="source.media_upload_failed",
                entity_type="source",
                entity_id=source.id,
                details_json={"kind": kind, "filename": file.filename},
            )
        )
        db.commit()
        raise HTTPException(status_code=500, detail="Media upload failed") from exc

    source.status = "uploaded"
    source.metadata_json = {
        "media": {
            "backend": stored.backend,
            "key": stored.key,
            "filename": stored.filename,
            "content_type": stored.content_type,
            "size": stored.size,
            "sha256": stored.sha256,
            "private": True,
        }
    }
    db.add(
        AuditLog(
            workspace_id=workspace.workspace.id,
            user_id=workspace.auth.user.id,
            action="source.media_uploaded",
            entity_type="source",
            entity_id=source.id,
            details_json={
                "kind": kind,
                "filename": stored.filename,
                "size": stored.size,
                "content_type": stored.content_type,
                "storage_backend": stored.backend,
            },
        )
    )
    db.commit()
    db.refresh(source)
    return source


@router.get("/library", response_model=SourceLibraryOut)
def source_library(
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> SourceLibraryOut:
    rows = db.execute(
        select(
            Source,
            func.count(Story.id).label("story_count"),
        )
        .outerjoin(Story, Story.source_id == Source.id)
        .where(Source.workspace_id == workspace.workspace.id)
        .group_by(Source.id)
        .order_by(Source.created_at.desc())
    ).all()

    items: list[SourceLibraryItemOut] = []
    for source, story_count in rows:
        media = dict((source.metadata_json or {}).get("media") or {})
        items.append(
            SourceLibraryItemOut(
                id=source.id,
                kind=source.kind,
                title=source.title,
                original_url=source.original_url,
                status=source.status,
                created_at=source.created_at,
                story_count=int(story_count or 0),
                has_transcript=bool(source.transcript_text),
                storage_filename=media.get("filename"),
                storage_size=media.get("size"),
                content_type=media.get("content_type"),
            )
        )

    indexed = sum(1 for item in items if item.status == "indexed")
    uploaded = sum(1 for item in items if item.status in {"uploaded", "uploading"})
    needs_attention = sum(
        1
        for item in items
        if item.status
        in {
            "needs_content",
            "needs_review",
            "fetch_failed",
            "upload_failed",
        }
    )
    return SourceLibraryOut(
        sources=items,
        total=len(items),
        indexed=indexed,
        uploaded=uploaded,
        needs_attention=needs_attention,
    )


@router.post("/{source_id}/transcribe", response_model=IngestionJobOut, status_code=202)
def queue_transcription(
    source_id: str,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> IngestionJob:
    source = db.get(Source, source_id)
    if not source or source.workspace_id != workspace.workspace.id:
        raise HTTPException(status_code=404, detail="Source not found")

    media = dict((source.metadata_json or {}).get("media") or {})
    if not media.get("key"):
        raise HTTPException(status_code=400, detail="Source does not contain stored media")
    if source.transcript_text and source.status == "indexed":
        raise HTTPException(status_code=409, detail="Source is already transcribed")

    existing = db.scalar(
        select(IngestionJob)
        .where(
            IngestionJob.workspace_id == workspace.workspace.id,
            IngestionJob.source_id == source.id,
            IngestionJob.job_type == "transcription",
            IngestionJob.status.in_(["queued", "processing"]),
        )
        .order_by(IngestionJob.created_at.desc())
    )
    if existing:
        return existing

    job = IngestionJob(
        workspace_id=workspace.workspace.id,
        source_id=source.id,
        job_type="transcription",
        provider=settings.transcription_provider,
        status="queued",
    )
    source.status = "transcription_queued"
    db.add(job)
    db.flush()
    db.add(
        AuditLog(
            workspace_id=workspace.workspace.id,
            user_id=workspace.auth.user.id,
            action="source.transcription_queued",
            entity_type="source",
            entity_id=source.id,
            details_json={"job_id": job.id, "provider": job.provider},
        )
    )
    db.commit()
    db.refresh(job)
    return job


@router.get("/{source_id}/transcription", response_model=SourceTranscriptOut)
def source_transcription(
    source_id: str,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> SourceTranscriptOut:
    source = db.get(Source, source_id)
    if not source or source.workspace_id != workspace.workspace.id:
        raise HTTPException(status_code=404, detail="Source not found")

    segments = list(
        db.scalars(
            select(SourceTranscriptSegment)
            .where(SourceTranscriptSegment.source_id == source.id)
            .order_by(SourceTranscriptSegment.sequence.asc())
        )
    )
    return SourceTranscriptOut(
        source_id=source.id,
        status=source.status,
        transcript_text=source.transcript_text,
        segments=[TranscriptSegmentOut.model_validate(segment) for segment in segments],
    )


@router.get("", response_model=list[SourceOut])
def list_sources(
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[Source]:
    stmt = (
        select(Source)
        .where(Source.workspace_id == workspace.workspace.id)
        .order_by(Source.created_at.desc())
    )
    return list(db.scalars(stmt))


@router.get("/{source_id}", response_model=SourceOut)
def get_source(
    source_id: str,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> Source:
    source = db.get(Source, source_id)
    if not source or source.workspace_id != workspace.workspace.id:
        raise HTTPException(status_code=404, detail="Source not found")
    return source
