from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Evidence, Source, Story, Workspace
from ..schemas import EvidenceCreate, EvidenceOut, StoryCreate, StoryOut

router = APIRouter(prefix="/stories", tags=["stories"])


@router.post("", response_model=StoryOut, status_code=201)
def create_story(payload: StoryCreate, db: Session = Depends(get_db)) -> Story:
    workspace = db.scalar(select(Workspace).where(Workspace.slug == payload.workspace_slug))
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    source = db.get(Source, payload.source_id)
    if not source or source.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Source not found in workspace")

    story = Story(
        workspace_id=workspace.id,
        source_id=source.id,
        title=payload.title,
        angle=payload.angle,
        signal_score=payload.signal_score,
        status="draft",
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return story


@router.get("", response_model=list[StoryOut])
def list_stories(
    workspace_slug: str = Query(default="demo"),
    db: Session = Depends(get_db),
) -> list[Story]:
    workspace = db.scalar(select(Workspace).where(Workspace.slug == workspace_slug))
    if not workspace:
        return []
    stmt = select(Story).where(Story.workspace_id == workspace.id).order_by(Story.created_at.desc())
    return list(db.scalars(stmt))


@router.get("/{story_id}", response_model=StoryOut)
def get_story(story_id: str, db: Session = Depends(get_db)) -> Story:
    story = db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.post("/{story_id}/evidence", response_model=EvidenceOut, status_code=201)
def add_evidence(story_id: str, payload: EvidenceCreate, db: Session = Depends(get_db)) -> Evidence:
    story = db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    item = Evidence(
        story_id=story.id,
        source_id=story.source_id,
        claim=payload.claim,
        excerpt=payload.excerpt,
        start_ms=payload.start_ms,
        end_ms=payload.end_ms,
        support_status="supported" if payload.excerpt else "needs_review",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{story_id}/evidence", response_model=list[EvidenceOut])
def list_evidence(story_id: str, db: Session = Depends(get_db)) -> list[Evidence]:
    story = db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    stmt = select(Evidence).where(Evidence.story_id == story_id).order_by(Evidence.created_at.asc())
    return list(db.scalars(stmt))
