from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Story, StoryOutput


router = APIRouter(prefix="/stories", tags=["editorial-state"])


class EditorialSelectionStateOut(BaseModel):
    story_id: str
    selection_id: str | None = None
    status: str
    headline: str | None = None
    mode: str | None = None
    angle_rank: int | None = None
    angle_title: str | None = None
    evidence: str | None = None
    location: str | None = None
    hook: str | None = None
    sourceguard_status: str | None = None
    verification_level: str | None = None
    grounding_score: int | None = None
    reasons: list[str] = Field(default_factory=list)
    custom_edit: bool = False
    approval: dict[str, Any] | None = None


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


@router.get("/{story_id}/editorial/selection-state", response_model=EditorialSelectionStateOut)
def editorial_selection_state(
    story_id: str,
    db: Session = Depends(get_db),
) -> EditorialSelectionStateOut:
    story = db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    selection = _latest_editorial_selection(db, story.id)
    if not selection:
        return EditorialSelectionStateOut(
            story_id=story.id,
            status="headline_required",
            headline=story.title,
        )

    content = dict(selection.content_json or {})
    approval = content.get("editorial_approval") if isinstance(content.get("editorial_approval"), dict) else None
    reasons = [str(item) for item in (content.get("reasons") or []) if str(item).strip()]

    if selection.status == "approved" or (approval and approval.get("status") == "approved"):
        status = "approved"
    elif selection.status == "ready" and content.get("sourceguard_status") == "source_aligned":
        status = "ready"
    else:
        status = "review_required"

    return EditorialSelectionStateOut(
        story_id=story.id,
        selection_id=selection.id,
        status=status,
        headline=content.get("headline") or story.title,
        mode=content.get("mode"),
        angle_rank=content.get("angle_rank"),
        angle_title=content.get("angle_title"),
        evidence=content.get("evidence"),
        location=content.get("location"),
        hook=content.get("hook"),
        sourceguard_status=content.get("sourceguard_status"),
        verification_level=content.get("verification_level"),
        grounding_score=content.get("grounding_score"),
        reasons=reasons,
        custom_edit=bool(content.get("custom_edit")),
        approval=approval,
    )
