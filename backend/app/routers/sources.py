from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Source, Workspace
from ..schemas import SourceCreate, SourceOut

router = APIRouter(prefix="/sources", tags=["sources"])


def get_or_create_workspace(db: Session, slug: str) -> Workspace:
    workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
    if workspace:
        return workspace
    workspace = Workspace(name=slug.replace("-", " ").title(), slug=slug)
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


@router.post("", response_model=SourceOut, status_code=201)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)) -> Source:
    workspace = get_or_create_workspace(db, payload.workspace_slug)
    source = Source(
        workspace_id=workspace.id,
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


@router.get("", response_model=list[SourceOut])
def list_sources(
    workspace_slug: str = Query(default="demo"),
    db: Session = Depends(get_db),
) -> list[Source]:
    workspace = db.scalar(select(Workspace).where(Workspace.slug == workspace_slug))
    if not workspace:
        return []
    stmt = select(Source).where(Source.workspace_id == workspace.id).order_by(Source.created_at.desc())
    return list(db.scalars(stmt))


@router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: str, db: Session = Depends(get_db)) -> Source:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source
