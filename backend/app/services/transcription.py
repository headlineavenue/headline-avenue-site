from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx

from ..config import get_settings
from .media_storage import local_media_path, presigned_media_url


settings = get_settings()


@dataclass(frozen=True)
class TranscriptSegmentResult:
    sequence: int
    start_ms: int
    end_ms: int
    speaker: str | None
    text: str
    confidence: float | None


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    segments: list[TranscriptSegmentResult]
    provider: str
    model: str
    request_id: str | None
    language: str | None
    duration_seconds: float | None


def _iter_file(path: Path, chunk_size: int = 1024 * 1024) -> Iterable[bytes]:
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            yield chunk


def _deepgram_params() -> dict[str, str]:
    params = {
        "model": settings.deepgram_model,
        "smart_format": "true",
        "punctuate": "true",
        "utterances": "true",
    }
    language = settings.deepgram_language.strip()
    if language:
        params["language"] = language
    if settings.deepgram_diarize:
        params["diarize_model"] = "latest"
    return params


def _parse_deepgram(payload: dict) -> TranscriptionResult:
    results = dict(payload.get("results") or {})
    channels = list(results.get("channels") or [])
    channel = dict(channels[0] or {}) if channels else {}
    alternatives = list(channel.get("alternatives") or [])
    alternative = dict(alternatives[0] or {}) if alternatives else {}

    text = str(alternative.get("transcript") or "").strip()
    utterances = list(results.get("utterances") or [])
    segments: list[TranscriptSegmentResult] = []

    for index, raw in enumerate(utterances):
        item = dict(raw or {})
        segment_text = str(item.get("transcript") or "").strip()
        if not segment_text:
            continue

        words = list(item.get("words") or [])
        confidences = [
            float(word.get("confidence"))
            for word in words
            if isinstance(word, dict) and word.get("confidence") is not None
        ]
        confidence = (
            sum(confidences) / len(confidences)
            if confidences
            else (
                float(item.get("confidence"))
                if item.get("confidence") is not None
                else None
            )
        )
        speaker_value = item.get("speaker")
        speaker = None if speaker_value is None else str(speaker_value)

        segments.append(
            TranscriptSegmentResult(
                sequence=len(segments),
                start_ms=max(0, round(float(item.get("start") or 0) * 1000)),
                end_ms=max(0, round(float(item.get("end") or 0) * 1000)),
                speaker=speaker,
                text=segment_text,
                confidence=confidence,
            )
        )

    if not text and segments:
        text = " ".join(segment.text for segment in segments).strip()

    metadata = dict(payload.get("metadata") or {})
    duration = metadata.get("duration")
    duration_seconds = float(duration) if duration is not None else None
    request_id = metadata.get("request_id")

    language = None
    for key in ("detected_language", "language"):
        value = channel.get(key)
        if value:
            language = str(value)
            break
    if not language:
        languages = metadata.get("languages")
        if isinstance(languages, list) and languages:
            language = str(languages[0])

    return TranscriptionResult(
        text=text,
        segments=segments,
        provider="deepgram",
        model=settings.deepgram_model,
        request_id=str(request_id) if request_id else None,
        language=language,
        duration_seconds=duration_seconds,
    )


def transcribe_media(media: dict) -> TranscriptionResult:
    provider = settings.transcription_provider.strip().lower()
    if provider != "deepgram":
        raise RuntimeError(f"Unsupported transcription provider: {provider}")

    if not settings.deepgram_api_key:
        raise RuntimeError("DEEPGRAM_API_KEY is not configured")

    key = str(media.get("key") or "")
    if not key:
        raise RuntimeError("Source does not have a stored media key")

    content_type = str(media.get("content_type") or "application/octet-stream")
    backend = str(media.get("backend") or settings.media_storage_backend).lower()

    url = settings.deepgram_api_base.rstrip("/") + "/v1/listen"
    headers = {"Authorization": f"Token {settings.deepgram_api_key}"}
    timeout = httpx.Timeout(connect=20.0, read=620.0, write=620.0, pool=20.0)

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        if backend == "local":
            path = local_media_path(key)
            response = client.post(
                url,
                params=_deepgram_params(),
                headers={**headers, "Content-Type": content_type},
                content=_iter_file(path),
            )
        elif backend in {"s3", "r2"}:
            response = client.post(
                url,
                params=_deepgram_params(),
                headers={**headers, "Content-Type": "application/json"},
                json={"url": presigned_media_url(key)},
            )
        else:
            raise RuntimeError(f"Unsupported media backend for transcription: {backend}")

    if response.status_code >= 400:
        detail = response.text[:1200]
        raise RuntimeError(
            f"Deepgram transcription failed ({response.status_code}): {detail}"
        )

    payload = response.json()
    result = _parse_deepgram(payload)
    if not result.text:
        raise RuntimeError("Transcription completed without transcript text")
    return result
