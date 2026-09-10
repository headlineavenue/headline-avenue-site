from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Source, Story, StoryOutput
from ..services.editorial_intelligence import build_editorial_variants
from ..services.source_intelligence import build_story_angles, extract_source_text


router = APIRouter(prefix="/stories", tags=["editorial-intelligence"])


class EditorialGenerateIn(BaseModel):
    angle_rank: int = Field(default=1, ge=1, le=10)


class EditorialVariantOut(BaseModel):
    mode: Literal["balanced", "breaking", "explainer", "social"]
    label: str
    headline: str
    hook: str
    sourceguard_status: Literal["source_aligned", "needs_review"]
    verification_level: str
    grounding_score: int = Field(ge=0, le=100)
    reasons: list[str]


class EditorialGenerateOut(BaseModel):
    story_id: str
    source_id: str
    angle_rank: int
    angle_title: str
    evidence: str
    location: str
    variants: list[EditorialVariantOut]
    message: str


class EditorialSelectIn(BaseModel):
    angle_rank: int = Field(default=1, ge=1, le=10)
    mode: Literal["balanced", "breaking", "explainer", "social"]


class EditorialSelectionOut(BaseModel):
    story_id: str
    output_id: str
    title: str
    mode: str
    status: str
    selected: EditorialVariantOut


def _load_angle(story: Story, source: Source, angle_rank: int) -> tuple[dict, str]:
    text = (source.transcript_text or "").strip()

    if not text:
        try:
            extracted = extract_source_text(
                kind=source.kind,
                original_url=source.original_url,
                transcript_text=source.transcript_text,
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"Source needs analysis first: {exc}") from exc
        text = extracted.text

    angles = build_story_angles(text, limit=max(3, angle_rank))
    if not angles or angle_rank > len(angles):
        raise HTTPException(status_code=404, detail="Requested story angle was not found")

    return angles[angle_rank - 1], text


@router.post("/{story_id}/editorial", response_model=EditorialGenerateOut)
def generate_editorial_variants(
    story_id: str,
    payload: EditorialGenerateIn,
    db: Session = Depends(get_db),
) -> EditorialGenerateOut:
    story = db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    source = db.get(Source, story.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    angle, _ = _load_angle(story, source, payload.angle_rank)
    variants = build_editorial_variants(angle)

    return EditorialGenerateOut(
        story_id=story.id,
        source_id=source.id,
        angle_rank=payload.angle_rank,
        angle_title=angle["title"],
        evidence=angle["excerpt"],
        location=angle["location"],
        variants=[EditorialVariantOut.model_validate(item) for item in variants],
        message=(
            f"Generated {len(variants)} source-grounded editorial variants. "
            "SourceGuard v1 checks lexical grounding; semantic verification remains a later layer."
        ),
    )


@router.post("/{story_id}/editorial/select", response_model=EditorialSelectionOut, status_code=201)
def select_editorial_variant(
    story_id: str,
    payload: EditorialSelectIn,
    db: Session = Depends(get_db),
) -> EditorialSelectionOut:
    story = db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    source = db.get(Source, story.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    angle, _ = _load_angle(story, source, payload.angle_rank)
    variants = build_editorial_variants(angle)
    selected = next((item for item in variants if item["mode"] == payload.mode), None)

    if not selected:
        raise HTTPException(status_code=404, detail="Requested editorial mode was not generated")

    output = StoryOutput(
        story_id=story.id,
        output_type="editorial_selection",
        status="ready" if selected["sourceguard_status"] == "source_aligned" else "needs_review",
        content_json={
            "angle_rank": payload.angle_rank,
            "angle_title": angle["title"],
            "evidence": angle["excerpt"],
            "location": angle["location"],
            **selected,
        },
    )
    db.add(output)

    story.title = selected["headline"]
    story.angle = angle["title"]
    story.signal_score = angle["score"]
    if story.status != "pack_ready":
        story.status = "editorial_ready" if output.status == "ready" else "needs_review"

    db.commit()
    db.refresh(output)
    db.refresh(story)

    return EditorialSelectionOut(
        story_id=story.id,
        output_id=output.id,
        title=story.title,
        mode=selected["mode"],
        status=output.status,
        selected=EditorialVariantOut.model_validate(selected),
    )
