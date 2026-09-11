from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Source, Story, StoryOutput


router = APIRouter(prefix="/publishing", tags=["publishing"])


class PublishDraftOut(BaseModel):
    id: str
    story_id: str
    headline: str
    caption: str
    source_label: str
    source_kind: str
    status: str
    editorial_status: str
    approval: dict[str, Any] | None = None
    formats: list[str] = Field(default_factory=list)
    output_ids: list[str] = Field(default_factory=list)
    created_at: datetime


def _latest_editorial_selection(db: Session, story_id: str) -> StoryOutput | None:
    return (
        db.query(StoryOutput)
        .filter(
            StoryOutput.story_id == story_id,
            StoryOutput.output_type == "editorial_selection",
        )
        .order_by(StoryOutput.created_at.desc(), StoryOutput.id.desc())
        .first()
    )


def _latest_pack_outputs(db: Session, story_id: str) -> list[StoryOutput]:
    rows = (
        db.query(StoryOutput)
        .filter(
            StoryOutput.story_id == story_id,
            StoryOutput.output_type.notin_(["editorial_selection", "publish_draft"]),
        )
        .order_by(StoryOutput.created_at.desc(), StoryOutput.id.desc())
        .all()
    )

    # A story may be regenerated several times. The publishing desk should use
    # only the newest version of each output type rather than showing stale
    # duplicates from earlier Story Pack runs.
    latest: list[StoryOutput] = []
    seen: set[str] = set()
    for row in rows:
        if row.output_type in seen:
            continue
        seen.add(row.output_type)
        latest.append(row)
    return latest


def _source_label(source: Source | None) -> str:
    if not source:
        return "Indexed source"
    if source.title:
        return source.title
    if source.original_url:
        return str(source.original_url)
    return "Indexed source"


def _draft_from_output(output: StoryOutput) -> PublishDraftOut:
    content = dict(output.content_json or {})
    return PublishDraftOut(
        id=output.id,
        story_id=output.story_id,
        headline=str(content.get("headline") or "Untitled story"),
        caption=str(content.get("caption") or ""),
        source_label=str(content.get("source_label") or "Indexed source"),
        source_kind=str(content.get("source_kind") or "source"),
        status=output.status,
        editorial_status=str(content.get("editorial_status") or "ready"),
        approval=content.get("approval") if isinstance(content.get("approval"), dict) else None,
        formats=[str(item) for item in (content.get("formats") or [])],
        output_ids=[str(item) for item in (content.get("output_ids") or [])],
        created_at=output.created_at,
    )


@router.post("/drafts/from-story/{story_id}", response_model=PublishDraftOut, status_code=201)
def create_publish_draft(story_id: str, db: Session = Depends(get_db)) -> PublishDraftOut:
    story = db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    selection = _latest_editorial_selection(db, story.id)
    if not selection:
        raise HTTPException(status_code=409, detail="Choose and save an editorial headline before publishing")

    editorial_content = dict(selection.content_json or {})
    approval = (
        editorial_content.get("editorial_approval")
        if isinstance(editorial_content.get("editorial_approval"), dict)
        else None
    )

    editor_approved = bool(
        selection.status == "approved"
        or (approval and approval.get("status") == "approved")
    )
    source_aligned = bool(
        selection.status == "ready"
        and editorial_content.get("sourceguard_status") == "source_aligned"
    )

    if not (editor_approved or source_aligned):
        raise HTTPException(
            status_code=409,
            detail="SourceGuard review must be resolved before the Story Pack can move to Publish",
        )

    outputs = _latest_pack_outputs(db, story.id)
    if not outputs:
        raise HTTPException(status_code=409, detail="Generate a Story Pack before moving to Publish")

    source = db.get(Source, story.source_id)
    headline = str(editorial_content.get("headline") or story.title)
    label = _source_label(source)
    caption = f"{headline}\n\nSource: {label}"
    editorial_status = "approved" if editor_approved else "ready"

    draft = StoryOutput(
        story_id=story.id,
        output_type="publish_draft",
        status="draft",
        content_json={
            "headline": headline,
            "caption": caption,
            "source_label": label,
            "source_kind": source.kind if source else "source",
            "editorial_status": editorial_status,
            "approval": approval,
            "formats": [output.output_type for output in outputs],
            "output_ids": [output.id for output in outputs],
            "editorial_selection_id": selection.id,
        },
    )
    db.add(draft)
    story.status = "publish_draft"
    db.commit()
    db.refresh(draft)

    return _draft_from_output(draft)


@router.get("/drafts/{story_id}", response_model=PublishDraftOut)
def get_latest_publish_draft(story_id: str, db: Session = Depends(get_db)) -> PublishDraftOut:
    story = db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    draft = (
        db.query(StoryOutput)
        .filter(
            StoryOutput.story_id == story.id,
            StoryOutput.output_type == "publish_draft",
        )
        .order_by(StoryOutput.created_at.desc(), StoryOutput.id.desc())
        .first()
    )
    if not draft:
        raise HTTPException(status_code=404, detail="Publish draft not found")
    return _draft_from_output(draft)
