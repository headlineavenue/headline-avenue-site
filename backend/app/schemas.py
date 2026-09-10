from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class WorkspaceOut(ORMModel):
    id: str
    name: str
    slug: str
    created_at: datetime


class SourceCreate(BaseModel):
    workspace_slug: str = "demo"
    kind: Literal["url", "video", "audio", "article", "pdf", "transcript"] = "url"
    title: str | None = None
    original_url: HttpUrl | None = None
    transcript_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceOut(ORMModel):
    id: str
    workspace_id: str
    kind: str
    title: str | None
    original_url: str | None
    status: str
    metadata_json: dict[str, Any]
    transcript_text: str | None
    created_at: datetime


class StoryCreate(BaseModel):
    workspace_slug: str = "demo"
    source_id: str
    title: str
    angle: str | None = None
    signal_score: float | None = Field(default=None, ge=0, le=100)


class StoryOut(ORMModel):
    id: str
    workspace_id: str
    source_id: str
    title: str
    angle: str | None
    signal_score: float | None
    status: str
    created_at: datetime


class EvidenceCreate(BaseModel):
    claim: str
    excerpt: str | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)


class EvidenceOut(ORMModel):
    id: str
    story_id: str
    source_id: str
    claim: str
    excerpt: str | None
    start_ms: int | None
    end_ms: int | None
    support_status: str
    created_at: datetime


class StoryAngleOut(BaseModel):
    rank: int
    score: float
    title: str
    claim: str
    excerpt: str
    location: str
    signal: str
    verification_level: Literal["direct_extract"]


class SourceGuardTraceOut(BaseModel):
    status: Literal["supported", "needs_review"]
    verification_level: str
    headline: str | None = None
    evidence: str | None = None
    location: str | None = None
    context: str


class StoryAnalysisOut(BaseModel):
    story_id: str
    source_id: str
    source_status: str
    extraction_method: str | None = None
    source_title: str | None = None
    source_characters: int = 0
    angles: list[StoryAngleOut] = Field(default_factory=list)
    sourceguard: SourceGuardTraceOut
    message: str


class StoryPackGenerate(BaseModel):
    story_id: str
    formats: list[str] = Field(default_factory=lambda: ["headline", "summary", "platform_copy"])


class StoryOutputOut(ORMModel):
    id: str
    story_id: str
    output_type: str
    aspect_ratio: str | None
    status: str
    content_json: dict[str, Any]
    created_at: datetime


class StoryPackOut(BaseModel):
    story_id: str
    outputs: list[StoryOutputOut]


class SourceGuardCheckIn(BaseModel):
    claim: str
    excerpt: str | None = None


class SourceGuardCheckOut(BaseModel):
    status: Literal["supported", "needs_review"]
    reasons: list[str]
