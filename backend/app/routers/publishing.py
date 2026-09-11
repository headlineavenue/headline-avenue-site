from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PublishingJob, Source, Story, StoryOutput


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


class PublishPlanIn(BaseModel):
    destinations: list[str] = Field(default_factory=list)
    mode: str = "now"
    scheduled_at: datetime | None = None
    title: str | None = None
    caption: str | None = None


class PublishDispatchIn(PublishPlanIn):
    confirmed: bool = False


class PublishCheckOut(BaseModel):
    code: str
    label: str
    status: str
    detail: str
    blocking: bool = False


class PublishPreflightOut(BaseModel):
    draft_id: str
    story_id: str
    can_dispatch: bool
    delivery_mode: str
    mode: str
    scheduled_at: datetime | None = None
    destinations: list[str] = Field(default_factory=list)
    fingerprint: str
    checks: list[PublishCheckOut] = Field(default_factory=list)


class PublishJobOut(BaseModel):
    id: str
    platform: str
    status: str
    scheduled_at: datetime | None = None
    external_id: str | None = None
    created_at: datetime


class PublishDispatchOut(BaseModel):
    dispatch_id: str
    draft_id: str
    story_id: str
    status: str
    delivery_mode: str
    fingerprint: str
    jobs: list[PublishJobOut] = Field(default_factory=list)
    created_at: datetime


class PublishJobsOut(BaseModel):
    story_id: str
    jobs: list[PublishJobOut] = Field(default_factory=list)


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
            StoryOutput.output_type.notin_([
                "editorial_selection",
                "publish_draft",
                "publish_dispatch",
            ]),
        )
        .order_by(StoryOutput.created_at.desc(), StoryOutput.id.desc())
        .all()
    )

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


def _get_publish_draft(db: Session, draft_id: str) -> StoryOutput:
    draft = db.get(StoryOutput, draft_id)
    if not draft or draft.output_type != "publish_draft":
        raise HTTPException(status_code=404, detail="Publish draft not found")
    return draft


def _normalize_destinations(values: list[str]) -> tuple[list[str], list[str]]:
    aliases = {
        "youtube": "youtube",
        "yt": "youtube",
        "instagram": "instagram",
        "ig": "instagram",
        "tiktok": "tiktok",
        "tt": "tiktok",
    }
    normalized: list[str] = []
    unknown: list[str] = []
    for raw in values:
        key = str(raw or "").strip().lower()
        platform = aliases.get(key)
        if not platform:
            if key:
                unknown.append(str(raw))
            continue
        if platform not in normalized:
            normalized.append(platform)
    return normalized, unknown


def _platform_label(platform: str) -> str:
    return {
        "youtube": "YouTube",
        "instagram": "Instagram",
        "tiktok": "TikTok",
    }.get(platform, platform.title())


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def _active_platforms(db: Session, story_id: str, destinations: list[str]) -> list[str]:
    if not destinations:
        return []
    rows = (
        db.query(PublishingJob)
        .join(StoryOutput, PublishingJob.story_output_id == StoryOutput.id)
        .filter(
            StoryOutput.story_id == story_id,
            StoryOutput.output_type == "publish_dispatch",
            PublishingJob.platform.in_(destinations),
            PublishingJob.status.in_(["queued", "scheduled", "publishing"]),
        )
        .all()
    )
    return sorted({row.platform for row in rows})


def _preflight(db: Session, draft: StoryOutput, payload: PublishPlanIn) -> PublishPreflightOut:
    content = dict(draft.content_json or {})
    stored_headline = str(content.get("headline") or "").strip()
    stored_caption = str(content.get("caption") or "").strip()
    title = str(payload.title if payload.title is not None else stored_headline).strip()
    caption = str(payload.caption if payload.caption is not None else stored_caption).strip()
    formats = [str(item) for item in (content.get("formats") or [])]
    output_ids = [str(item) for item in (content.get("output_ids") or [])]
    normalized, unknown = _normalize_destinations(payload.destinations)
    mode = str(payload.mode or "now").lower()
    scheduled_at = _aware(payload.scheduled_at)
    checks: list[PublishCheckOut] = []

    def add(code: str, label: str, status: str, detail: str, blocking: bool = False) -> None:
        checks.append(PublishCheckOut(code=code, label=label, status=status, detail=detail, blocking=blocking))

    editorial_status = str(content.get("editorial_status") or "")
    if editorial_status in {"approved", "ready"}:
        if editorial_status == "approved":
            add("editorial_gate", "Editorial gate", "pass", "Editor-approved SourceGuard review is attached to this Story Pack.")
        else:
            add("editorial_gate", "Editorial gate", "pass", "The selected headline is source-aligned and publish-ready.")
    else:
        add("editorial_gate", "Editorial gate", "fail", "SourceGuard review is unresolved.", True)

    if formats and output_ids:
        add("story_pack", "Story Pack", "pass", f"{len(formats)} generated assets are attached to this draft.")
    else:
        add("story_pack", "Story Pack", "fail", "Generate a Story Pack before distribution.", True)

    if unknown:
        add("destinations", "Destinations", "fail", "Unknown destination: " + ", ".join(unknown), True)
    elif not normalized:
        add("destinations", "Destinations", "fail", "Choose at least one destination.", True)
    elif "tiktok" in normalized:
        add("destinations", "Destinations", "fail", "TikTok is still sandbox-only and cannot enter the production queue.", True)
    else:
        add("destinations", "Destinations", "pass", ", ".join(_platform_label(item) for item in normalized) + " selected.")

    if not title:
        add("copy_snapshot", "Approved copy", "fail", "A headline is required.", True)
    elif title != stored_headline or caption != stored_caption:
        add(
            "copy_snapshot",
            "Approved copy",
            "fail",
            "Publish copy changed after editorial approval. Return to Story Workspace so the revised wording can be checked before distribution.",
            True,
        )
    elif len(title) > 500 or len(caption) > 5000:
        add("copy_snapshot", "Approved copy", "fail", "Publish copy exceeds Headline Avenue's current distribution limits.", True)
    else:
        add("copy_snapshot", "Approved copy", "pass", "Headline and caption match the approved Story Pack snapshot.")

    lower_formats = [item.lower() for item in formats]
    if "youtube" in normalized and not any("video" in item for item in lower_formats):
        add("asset_routing", "Asset routing", "fail", "YouTube requires a generated video asset.", True)
    elif "instagram" in normalized and not any(("video" in item) or item == "carousel" for item in lower_formats):
        add("asset_routing", "Asset routing", "fail", "Instagram requires a generated video or carousel asset.", True)
    else:
        add("asset_routing", "Asset routing", "pass", "Generated formats are compatible with the selected destinations.")

    if mode == "now":
        add("timing", "Send time", "pass", "Queue immediately after final confirmation.")
    elif mode == "later":
        if scheduled_at is None:
            add("timing", "Send time", "fail", "Choose a future date and time.", True)
        elif scheduled_at <= datetime.now(timezone.utc):
            add("timing", "Send time", "fail", "Scheduled time must be in the future.", True)
        else:
            add("timing", "Send time", "pass", f"Scheduled for {scheduled_at.isoformat()}.")
    else:
        add("timing", "Send time", "fail", "Unsupported publishing mode.", True)

    active = _active_platforms(db, draft.story_id, normalized)
    if active:
        add(
            "duplicate_guard",
            "Duplicate guard",
            "fail",
            "An active delivery job already exists for " + ", ".join(_platform_label(item) for item in active) + ".",
            True,
        )
    else:
        add("duplicate_guard", "Duplicate guard", "pass", "No active duplicate delivery jobs were found.")

    if "source_trail" in lower_formats:
        add("source_trail", "Source trail", "pass", "Source provenance is attached to the Story Pack.")
    else:
        add("source_trail", "Source trail", "warn", "Source trail is not a generated asset in this pack; editorial evidence still remains on the story.")

    add(
        "delivery_adapter",
        "Delivery layer",
        "warn",
        "This build creates durable platform jobs in Headline Avenue. External provider adapters are the next integration layer, so nothing leaves the app yet.",
    )

    snapshot = {
        "draft_id": draft.id,
        "story_id": draft.story_id,
        "headline": title,
        "caption": caption,
        "source_label": content.get("source_label"),
        "formats": formats,
        "output_ids": output_ids,
        "editorial_status": editorial_status,
        "approval": content.get("approval"),
        "destinations": normalized,
        "mode": mode,
        "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
    }
    fingerprint = _fingerprint(snapshot)
    can_dispatch = not any(check.blocking and check.status == "fail" for check in checks)

    return PublishPreflightOut(
        draft_id=draft.id,
        story_id=draft.story_id,
        can_dispatch=can_dispatch,
        delivery_mode="backend_queue",
        mode=mode,
        scheduled_at=scheduled_at,
        destinations=normalized,
        fingerprint=fingerprint,
        checks=checks,
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
    approval = editorial_content.get("editorial_approval") if isinstance(editorial_content.get("editorial_approval"), dict) else None

    editor_approved = bool(selection.status == "approved" or (approval and approval.get("status") == "approved"))
    source_aligned = bool(selection.status == "ready" and editorial_content.get("sourceguard_status") == "source_aligned")

    if not (editor_approved or source_aligned):
        raise HTTPException(status_code=409, detail="SourceGuard review must be resolved before the Story Pack can move to Publish")

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
        .filter(StoryOutput.story_id == story.id, StoryOutput.output_type == "publish_draft")
        .order_by(StoryOutput.created_at.desc(), StoryOutput.id.desc())
        .first()
    )
    if not draft:
        raise HTTPException(status_code=404, detail="Publish draft not found")
    return _draft_from_output(draft)


@router.post("/drafts/{draft_id}/preflight", response_model=PublishPreflightOut)
def preflight_publish_draft(draft_id: str, payload: PublishPlanIn, db: Session = Depends(get_db)) -> PublishPreflightOut:
    draft = _get_publish_draft(db, draft_id)
    return _preflight(db, draft, payload)


@router.post("/drafts/{draft_id}/dispatch", response_model=PublishDispatchOut, status_code=201)
def dispatch_publish_draft(draft_id: str, payload: PublishDispatchIn, db: Session = Depends(get_db)) -> PublishDispatchOut:
    draft = _get_publish_draft(db, draft_id)
    if not payload.confirmed:
        raise HTTPException(status_code=409, detail="Final confirmation is required before distribution jobs can be created")

    preflight = _preflight(db, draft, payload)
    if not preflight.can_dispatch:
        failed = [check.detail for check in preflight.checks if check.blocking and check.status == "fail"]
        raise HTTPException(status_code=409, detail="Preflight failed: " + " ".join(failed))

    content = dict(draft.content_json or {})
    title = str(payload.title if payload.title is not None else content.get("headline") or "").strip()
    caption = str(payload.caption if payload.caption is not None else content.get("caption") or "").strip()
    scheduled_at = _aware(payload.scheduled_at)
    status = "scheduled" if preflight.mode == "later" else "queued"
    now = datetime.now(timezone.utc)

    dispatch = StoryOutput(
        story_id=draft.story_id,
        output_type="publish_dispatch",
        status=status,
        content_json={
            "publish_draft_id": draft.id,
            "headline": title,
            "caption": caption,
            "source_label": content.get("source_label"),
            "source_kind": content.get("source_kind"),
            "editorial_status": content.get("editorial_status"),
            "approval": content.get("approval"),
            "formats": content.get("formats") or [],
            "output_ids": content.get("output_ids") or [],
            "destinations": preflight.destinations,
            "mode": preflight.mode,
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "fingerprint": preflight.fingerprint,
            "confirmed_at": now.isoformat(),
            "delivery_mode": "backend_queue",
        },
    )
    db.add(dispatch)
    db.flush()

    jobs: list[PublishingJob] = []
    for platform in preflight.destinations:
        job = PublishingJob(
            story_output_id=dispatch.id,
            platform=platform,
            status=status,
            scheduled_at=scheduled_at if status == "scheduled" else None,
        )
        db.add(job)
        jobs.append(job)

    story = db.get(Story, draft.story_id)
    if story:
        story.status = "scheduled" if status == "scheduled" else "queued_for_publish"

    db.commit()
    db.refresh(dispatch)
    for job in jobs:
        db.refresh(job)

    return PublishDispatchOut(
        dispatch_id=dispatch.id,
        draft_id=draft.id,
        story_id=draft.story_id,
        status=status,
        delivery_mode="backend_queue",
        fingerprint=preflight.fingerprint,
        jobs=[
            PublishJobOut(
                id=job.id,
                platform=job.platform,
                status=job.status,
                scheduled_at=job.scheduled_at,
                external_id=job.external_id,
                created_at=job.created_at,
            ) for job in jobs
        ],
        created_at=dispatch.created_at,
    )


@router.get("/jobs/{story_id}", response_model=PublishJobsOut)
def get_publish_jobs(story_id: str, db: Session = Depends(get_db)) -> PublishJobsOut:
    story = db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    rows = (
        db.query(PublishingJob)
        .join(StoryOutput, PublishingJob.story_output_id == StoryOutput.id)
        .filter(StoryOutput.story_id == story_id, StoryOutput.output_type == "publish_dispatch")
        .order_by(PublishingJob.created_at.desc(), PublishingJob.id.desc())
        .all()
    )

    return PublishJobsOut(
        story_id=story_id,
        jobs=[
            PublishJobOut(
                id=row.id,
                platform=row.platform,
                status=row.status,
                scheduled_at=row.scheduled_at,
                external_id=row.external_id,
                created_at=row.created_at,
            ) for row in rows
        ],
    )
