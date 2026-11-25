from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Evidence,
    PublishingJob,
    Source,
    SourceTranscriptSegment,
    Story,
    StoryOutput,
)
from ..schemas import (
    EvidenceCreate,
    EvidenceOut,
    SourceGuardTraceOut,
    StoryAnalysisOut,
    StoryCreate,
    StoryDeskItemOut,
    StoryDeskOut,
    StoryOut,
)
from ..services.source_intelligence import build_story_angles, extract_source_text
from ..security import WorkspaceContext, get_workspace_context

router = APIRouter(prefix="/stories", tags=["stories"])


def _format_ms(value: int) -> str:
    total_ms = max(0, int(value))
    minutes, remainder = divmod(total_ms, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def _timestamp_angles(
    *,
    text: str,
    angles: list[dict],
    segments: list[SourceTranscriptSegment],
    source_kind: str,
) -> list[dict]:
    if source_kind not in {"video", "audio"} or not segments or not text:
        return angles

    spans: list[tuple[int, int, SourceTranscriptSegment]] = []
    cursor = 0
    for segment in segments:
        segment_text = " ".join((segment.text or "").split()).strip()
        if not segment_text:
            continue
        start = text.find(segment_text, cursor)
        if start < 0:
            start = text.find(segment_text)
        if start < 0:
            continue
        end = start + len(segment_text)
        spans.append((start, end, segment))
        cursor = end

    if not spans:
        return angles

    for angle in angles:
        start_char = int(angle.get("source_start_char") or 0)
        end_char = int(angle.get("source_end_char") or start_char)
        overlapping = [
            segment
            for span_start, span_end, segment in spans
            if span_end > start_char and span_start < end_char
        ]
        if not overlapping:
            continue

        start_ms = min(segment.start_ms for segment in overlapping)
        end_ms = max(segment.end_ms for segment in overlapping)
        speakers = [segment.speaker for segment in overlapping if segment.speaker is not None]
        speaker = speakers[0] if speakers and len(set(speakers)) == 1 else None

        angle["start_ms"] = start_ms
        angle["end_ms"] = end_ms
        angle["speaker"] = speaker

        media_label = "Video" if source_kind == "video" else "Audio"
        speaker_label = f" · Speaker {speaker}" if speaker is not None else ""
        angle["location"] = (
            f"{media_label} · {_format_ms(start_ms)}–{_format_ms(end_ms)}{speaker_label}"
        )

    return angles


@router.post("", response_model=StoryOut, status_code=201)
def create_story(
    payload: StoryCreate,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> Story:
    source = db.get(Source, payload.source_id)
    if not source or source.workspace_id != workspace.workspace.id:
        raise HTTPException(status_code=404, detail="Source not found in workspace")

    story = Story(
        workspace_id=workspace.workspace.id,
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
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[Story]:
    stmt = (
        select(Story)
        .where(Story.workspace_id == workspace.workspace.id)
        .order_by(Story.created_at.desc())
    )
    return list(db.scalars(stmt))


@router.get("/desk", response_model=StoryDeskOut)
def story_desk(
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> StoryDeskOut:
    asset_types_excluded = ("editorial_selection", "publish_draft", "publish_dispatch")

    rows = db.execute(
        select(
            Story,
            Source,
            func.count(StoryOutput.id).label("output_count"),
        )
        .join(Source, Source.id == Story.source_id)
        .outerjoin(
            StoryOutput,
            and_(
                StoryOutput.story_id == Story.id,
                StoryOutput.output_type.notin_(asset_types_excluded),
            ),
        )
        .where(Story.workspace_id == workspace.workspace.id)
        .group_by(Story.id, Source.id)
        .order_by(Story.created_at.desc())
    ).all()

    story_ids = [story.id for story, _source, _count in rows]
    editorial_by_story: dict[str, StoryOutput] = {}
    publish_by_story: dict[str, list[PublishingJob]] = {story_id: [] for story_id in story_ids}

    if story_ids:
        editorial_rows = db.scalars(
            select(StoryOutput)
            .where(
                StoryOutput.story_id.in_(story_ids),
                StoryOutput.output_type == "editorial_selection",
            )
            .order_by(StoryOutput.story_id.asc(), StoryOutput.created_at.desc(), StoryOutput.id.desc())
        ).all()
        for output in editorial_rows:
            editorial_by_story.setdefault(output.story_id, output)

        job_rows = db.execute(
            select(PublishingJob, StoryOutput.story_id)
            .join(StoryOutput, StoryOutput.id == PublishingJob.story_output_id)
            .where(StoryOutput.story_id.in_(story_ids))
            .order_by(PublishingJob.created_at.desc())
        ).all()
        for job, story_id in job_rows:
            publish_by_story.setdefault(story_id, []).append(job)

    items: list[StoryDeskItemOut] = []
    for story, source, output_count in rows:
        editorial = editorial_by_story.get(story.id)
        editorial_content = dict(editorial.content_json or {}) if editorial else {}
        editorial_approval = editorial_content.get("editorial_approval")
        if editorial and (
            editorial.status in {"ready", "approved"}
            or (
                isinstance(editorial_approval, dict)
                and editorial_approval.get("status") == "approved"
            )
        ):
            sourceguard_status = "supported"
        elif editorial and editorial.status == "needs_review":
            sourceguard_status = "needs_review"
        elif story.status in {"analyzed", "editorial_ready", "pack_ready", "queued_for_publish", "scheduled"}:
            sourceguard_status = "supported"
        else:
            sourceguard_status = "pending"

        jobs = publish_by_story.get(story.id, [])
        scheduled_count = sum(1 for job in jobs if job.status == "scheduled")
        if scheduled_count:
            publish_status = "scheduled"
        elif any(job.status in {"queued", "publishing"} for job in jobs):
            publish_status = "queued"
        elif any(job.status == "published" for job in jobs):
            publish_status = "published"
        elif any(job.status in {"failed", "blocked"} for job in jobs):
            publish_status = "blocked"
        else:
            publish_status = "drafting"

        items.append(
            StoryDeskItemOut(
                id=story.id,
                source_id=story.source_id,
                title=story.title,
                angle=story.angle,
                signal_score=story.signal_score,
                story_status=story.status,
                created_at=story.created_at,
                source_title=source.title,
                source_kind=source.kind,
                source_status=source.status,
                output_count=int(output_count or 0),
                sourceguard_status=sourceguard_status,
                publish_status=publish_status,
                scheduled_count=scheduled_count,
            )
        )

    def is_review(item: StoryDeskItemOut) -> bool:
        return item.story_status == "needs_review" or item.sourceguard_status == "needs_review"

    def is_scheduled(item: StoryDeskItemOut) -> bool:
        return item.publish_status == "scheduled" or item.story_status == "scheduled"

    needs_review = sum(1 for item in items if is_review(item))
    scheduled = sum(1 for item in items if is_scheduled(item))
    active = sum(1 for item in items if not is_review(item) and not is_scheduled(item))
    story_packs = sum(item.output_count for item in items)

    return StoryDeskOut(
        stories=items,
        total=len(items),
        active=active,
        needs_review=needs_review,
        scheduled=scheduled,
        story_packs=story_packs,
    )


@router.get("/{story_id}", response_model=StoryOut)
def get_story(
    story_id: str,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> Story:
    story = db.get(Story, story_id)
    if not story or story.workspace_id != workspace.workspace.id:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.post("/{story_id}/analyze", response_model=StoryAnalysisOut)
def analyze_story(
    story_id: str,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> StoryAnalysisOut:
    story = db.get(Story, story_id)
    if not story or story.workspace_id != workspace.workspace.id:
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
    transcript_segments = list(
        db.scalars(
            select(SourceTranscriptSegment)
            .where(SourceTranscriptSegment.source_id == source.id)
            .order_by(SourceTranscriptSegment.sequence.asc())
        )
    )
    angles = _timestamp_angles(
        text=extracted.text,
        angles=angles,
        segments=transcript_segments,
        source_kind=source.kind,
    )
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
                start_ms=angle.get("start_ms"),
                end_ms=angle.get("end_ms"),
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
            start_ms=top.get("start_ms"),
            end_ms=top.get("end_ms"),
            speaker=top.get("speaker"),
            context=(
                "This candidate is derived directly from indexed source text. "
                "Semantic claim verification is still a later SourceGuard layer."
            ),
        ),
        message=f"Indexed source text and ranked {len(angles)} source-grounded story angles.",
    )


@router.post("/{story_id}/evidence", response_model=EvidenceOut, status_code=201)
def add_evidence(
    story_id: str,
    payload: EvidenceCreate,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> Evidence:
    story = db.get(Story, story_id)
    if not story or story.workspace_id != workspace.workspace.id:
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
def list_evidence(
    story_id: str,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[Evidence]:
    story = db.get(Story, story_id)
    if not story or story.workspace_id != workspace.workspace.id:
        raise HTTPException(status_code=404, detail="Story not found")
    stmt = select(Evidence).where(Evidence.story_id == story_id).order_by(Evidence.created_at.asc())
    return list(db.scalars(stmt))
