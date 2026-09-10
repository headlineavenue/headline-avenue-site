from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Evidence, Source, Story, Workspace
from ..schemas import (
    EvidenceCreate,
    EvidenceOut,
    SourceGuardTraceOut,
    StoryAnalysisOut,
    StoryCreate,
    StoryOut,
)
from ..services.source_intelligence import build_story_angles, extract_source_text

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


@router.post("/{story_id}/analyze", response_model=StoryAnalysisOut)
def analyze_story(story_id: str, db: Session = Depends(get_db)) -> StoryAnalysisOut:
    story = db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    source = db.get(Source, story.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    try:
        extracted = extract_source_text(
            kind=source.kind,
            original_url=source.original_url,
            transcript_text=source.transcript_text,
        )
    except (ValueError, RuntimeError) as exc:
        source.status = "needs_content"
        db.commit()
        return StoryAnalysisOut(
            story_id=story.id,
            source_id=source.id,
            source_status=source.status,
            extraction_method=None,
            source_title=source.title,
            source_characters=0,
            angles=[],
            sourceguard=SourceGuardTraceOut(
                status="needs_review",
                verification_level="unavailable",
                headline=None,
                evidence=None,
                location=None,
                context=str(exc),
            ),
            message=str(exc),
        )
    except Exception as exc:
        source.status = "fetch_failed"
        db.commit()
        return StoryAnalysisOut(
            story_id=story.id,
            source_id=source.id,
            source_status=source.status,
            extraction_method=None,
            source_title=source.title,
            source_characters=0,
            angles=[],
            sourceguard=SourceGuardTraceOut(
                status="needs_review",
                verification_level="unavailable",
                headline=None,
                evidence=None,
                location=None,
                context=f"Source extraction failed: {exc}",
            ),
            message=f"Source extraction failed: {exc}",
        )

    angles = build_story_angles(extracted.text, limit=3)
    if not angles:
        source.status = "needs_review"
        source.transcript_text = extracted.text
        db.commit()
        return StoryAnalysisOut(
            story_id=story.id,
            source_id=source.id,
            source_status=source.status,
            extraction_method=extracted.method,
            source_title=extracted.title or source.title,
            source_characters=len(extracted.text),
            angles=[],
            sourceguard=SourceGuardTraceOut(
                status="needs_review",
                verification_level="direct_extract",
                headline=None,
                evidence=None,
                location=None,
                context="Readable source text was indexed, but no strong sentence-level story angles were found.",
            ),
            message="Source indexed, but no strong story angles were found.",
        )

    # Persist the normalized source text and extraction provenance.
    source.transcript_text = extracted.text
    source.status = "indexed"
    metadata = dict(source.metadata_json or {})
    metadata["extraction"] = {
        "method": extracted.method,
        "content_type": extracted.content_type,
        "characters": len(extracted.text),
        "source_title": extracted.title,
    }
    metadata["analysis"] = {
        "engine": "deterministic-source-intelligence-v2",
        "angle_count": len(angles),
        "top_score": angles[0]["score"],
    }
    source.metadata_json = metadata

    if extracted.title and (not source.title or source.title.endswith(" source") or source.title.endswith(" article")):
        source.title = extracted.title[:500]

    # Add direct-extract evidence without duplicating the same claim on repeated analysis.
    existing_claims = set(
        db.scalars(select(Evidence.claim).where(Evidence.story_id == story.id)).all()
    )
    for angle in angles:
        if angle["claim"] in existing_claims:
            continue
        db.add(
            Evidence(
                story_id=story.id,
                source_id=source.id,
                claim=angle["claim"],
                excerpt=angle["excerpt"],
                support_status="supported",
            )
        )

    story.angle = angles[0]["title"]
    story.signal_score = angles[0]["score"]
    if story.status != "pack_ready":
        story.status = "analyzed"

    db.commit()
    db.refresh(source)
    db.refresh(story)

    top = angles[0]
    return StoryAnalysisOut(
        story_id=story.id,
        source_id=source.id,
        source_status=source.status,
        extraction_method=extracted.method,
        source_title=source.title,
        source_characters=len(extracted.text),
        angles=angles,
        sourceguard=SourceGuardTraceOut(
            status="supported",
            verification_level="direct_extract",
            headline=top["title"],
            evidence=top["excerpt"],
            location=top["location"],
            context=(
                "This candidate is derived directly from indexed source text. "
                "Semantic claim verification is still a later SourceGuard layer."
            ),
        ),
        message=f"Indexed source text and ranked {len(angles)} source-grounded story angles.",
    )


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
