from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Source
from ..schemas import SourceCreate, SourceOut
from ..security import WorkspaceContext, get_workspace_context

router = APIRouter(prefix="/sources", tags=["sources"])


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
