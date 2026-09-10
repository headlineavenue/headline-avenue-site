from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Source, Story, StoryOutput
from ..services.editorial_intelligence import (
    build_custom_editorial_variant,
    build_editorial_variants,
)
from ..services.source_intelligence import build_story_angles, extract_source_text


router = APIRouter(prefix="/stories", tags=["editorial-intelligence"])

EditorialMode = Literal["balanced", "breaking", "explainer", "social"]


class EditorialGenerateIn(BaseModel):
    angle_rank: int = Field(default=1, ge=1, le=10)
    generation: int = Field(default=1, ge=0, le=20)


class EditorialVariantOut(BaseModel):
    mode: EditorialMode
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
    generation: int
    angle_title: str
    evidence: str
    location: str
    variants: list[EditorialVariantOut]
    message: str


class EditorialSelectIn(BaseModel):
    angle_rank: int = Field(default=1, ge=1, le=10)
    mode: EditorialMode
    generation: int = Field(default=1, ge=0, le=20)


class EditorialCheckIn(BaseModel):
    angle_rank: int = Field(default=1, ge=1, le=10)
    mode: EditorialMode
    headline: str = Field(min_length=1, max_length=180)


class EditorialCheckOut(BaseModel):
    story_id: str
    angle_rank: int
    selected: EditorialVariantOut


class EditorialCustomSelectIn(BaseModel):
    angle_rank: int = Field(default=1, ge=1, le=10)
    mode: EditorialMode
    headline: str = Field(min_length=1, max_length=180)


class EditorialSelectionOut(BaseModel):
    story_id: str
    output_id: str
    title: str
    mode: str
    status: str
    selected: EditorialVariantOut


def _load_story_and_source(db: Session, story_id: str) -> tuple[Story, Source]:
    story = db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    source = db.get(Source, story.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    return story, source


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


def _persist_selection(
    db: Session,
    story: Story,
    angle: dict,
    selected: dict,
    angle_rank: int,
    custom: bool = False,
) -> EditorialSelectionOut:
    output_status = "ready" if selected["sourceguard_status"] == "source_aligned" else "needs_review"

    output = StoryOutput(
        story_id=story.id,
        output_type="editorial_selection",
        status=output_status,
        content_json={
            "angle_rank": angle_rank,
            "angle_title": angle["title"],
            "evidence": angle["excerpt"],
            "location": angle["location"],
            "custom_edit": custom,
            **selected,
        },
    )
    db.add(output)

    story.title = selected["headline"]
    story.angle = angle["title"]
    story.signal_score = angle["score"]
    if story.status != "pack_ready":
        story.status = "editorial_ready" if output_status == "ready" else "needs_review"

    db.commit()
    db.refresh(output)
    db.refresh(story)

    return EditorialSelectionOut(
        story_id=story.id,
        output_id=output.id,
        title=story.title,
        mode=selected["mode"],
        status=output_status,
        selected=EditorialVariantOut.model_validate(selected),
    )


@router.post("/{story_id}/editorial", response_model=EditorialGenerateOut)
def generate_editorial_variants(
    story_id: str,
    payload: EditorialGenerateIn,
    db: Session = Depends(get_db),
) -> EditorialGenerateOut:
    story, source = _load_story_and_source(db, story_id)
    angle, source_text = _load_angle(story, source, payload.angle_rank)
    variants = build_editorial_variants(
        angle,
        source_text=source_text,
        generation=payload.generation,
    )

    return EditorialGenerateOut(
        story_id=story.id,
        source_id=source.id,
        angle_rank=payload.angle_rank,
        generation=payload.generation,
        angle_title=angle["title"],
        evidence=angle["excerpt"],
        location=angle["location"],
        variants=[EditorialVariantOut.model_validate(item) for item in variants],
        message=(
            f"Generated {len(variants)} source-grounded editorial variants. "
            "Headline Lab v3 differentiates editorial modes and SourceGuard v3 checks "
            "the selected evidence plus indexed source context."
        ),
    )


@router.post("/{story_id}/editorial/check", response_model=EditorialCheckOut)
def check_custom_headline(
    story_id: str,
    payload: EditorialCheckIn,
    db: Session = Depends(get_db),
) -> EditorialCheckOut:
    story, source = _load_story_and_source(db, story_id)
    angle, source_text = _load_angle(story, source, payload.angle_rank)

    checked = build_custom_editorial_variant(
        headline=payload.headline,
        mode=payload.mode,
        evidence=angle["excerpt"],
        source_text=source_text,
    )

    return EditorialCheckOut(
        story_id=story.id,
        angle_rank=payload.angle_rank,
        selected=EditorialVariantOut.model_validate(checked),
    )


@router.post("/{story_id}/editorial/select", response_model=EditorialSelectionOut, status_code=201)
def select_editorial_variant(
    story_id: str,
    payload: EditorialSelectIn,
    db: Session = Depends(get_db),
) -> EditorialSelectionOut:
    story, source = _load_story_and_source(db, story_id)
    angle, source_text = _load_angle(story, source, payload.angle_rank)
    variants = build_editorial_variants(
        angle,
        source_text=source_text,
        generation=payload.generation,
    )
    selected = next((item for item in variants if item["mode"] == payload.mode), None)

    if not selected:
        raise HTTPException(status_code=404, detail="Requested editorial mode was not generated")

    return _persist_selection(
        db=db,
        story=story,
        angle=angle,
        selected=selected,
        angle_rank=payload.angle_rank,
        custom=False,
    )


@router.post("/{story_id}/editorial/select-custom", response_model=EditorialSelectionOut, status_code=201)
def select_custom_editorial_variant(
    story_id: str,
    payload: EditorialCustomSelectIn,
    db: Session = Depends(get_db),
) -> EditorialSelectionOut:
    story, source = _load_story_and_source(db, story_id)
    angle, source_text = _load_angle(story, source, payload.angle_rank)

    selected = build_custom_editorial_variant(
        headline=payload.headline,
        mode=payload.mode,
        evidence=angle["excerpt"],
        source_text=source_text,
    )

    return _persist_selection(
        db=db,
        story=story,
        angle=angle,
        selected=selected,
        angle_rank=payload.angle_rank,
        custom=True,
    )
