from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    sources: Mapped[list["Source"]] = relationship(back_populates="workspace")
    stories: Mapped[list["Story"]] = relationship(back_populates="workspace")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="url", index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    workspace: Mapped["Workspace"] = relationship(back_populates="sources")
    stories: Mapped[list["Story"]] = relationship(back_populates="source")
    evidence_items: Mapped[list["Evidence"]] = relationship(back_populates="source")


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    angle: Mapped[str | None] = mapped_column(Text, nullable=True)
    signal_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    workspace: Mapped["Workspace"] = relationship(back_populates="stories")
    source: Mapped["Source"] = relationship(back_populates="stories")
    evidence_items: Mapped[list["Evidence"]] = relationship(back_populates="story")
    outputs: Mapped[list["StoryOutput"]] = relationship(back_populates="story")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    support_status: Mapped[str] = mapped_column(String(40), default="unreviewed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    story: Mapped["Story"] = relationship(back_populates="evidence_items")
    source: Mapped["Source"] = relationship(back_populates="evidence_items")


class StoryOutput(Base):
    __tablename__ = "story_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), index=True)
    output_type: Mapped[str] = mapped_column(String(60), index=True)
    aspect_ratio: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    story: Mapped["Story"] = relationship(back_populates="outputs")
    publishing_jobs: Mapped[list["PublishingJob"]] = relationship(back_populates="output")


class PublishingJob(Base):
    __tablename__ = "publishing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_output_id: Mapped[str] = mapped_column(ForeignKey("story_outputs.id"), index=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    output: Mapped["StoryOutput"] = relationship(back_populates="publishing_jobs")
