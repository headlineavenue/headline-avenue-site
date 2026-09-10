from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (compatible; HeadlineAvenueBot/0.1; "
    "+https://headlineavenue.github.io/headline-avenue-site/)"
)
MAX_SOURCE_CHARS = 120_000


@dataclass
class ExtractedSource:
    text: str
    title: str | None
    method: str
    content_type: str | None = None


def _clean_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\r\n?", "\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _extract_html_text(raw_html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(raw_html, "html.parser")

    title = None
    if soup.title and soup.title.string:
        title = _clean_text(soup.title.string)

    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer"]):
        tag.decompose()

    preferred = soup.find("article") or soup.find("main") or soup.body or soup
    text = _clean_text(preferred.get_text("\n", strip=True))
    return text, title


def extract_source_text(kind: str, original_url: str | None, transcript_text: str | None) -> ExtractedSource:
    if transcript_text and transcript_text.strip():
        text = _clean_text(transcript_text)
        return ExtractedSource(
            text=text[:MAX_SOURCE_CHARS],
            title=None,
            method="provided_text",
            content_type="text/plain",
        )

    if not original_url:
        raise ValueError("This source has no text or public URL to analyze yet.")

    parsed = urlparse(original_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https source URLs can be fetched.")

    if parsed.hostname and parsed.hostname.lower() in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
    }:
        raise ValueError(
            "YouTube source extraction is not connected yet. Paste a transcript for now."
        )

    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(15.0, connect=8.0),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.2"},
    ) as client:
        response = client.get(original_url)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type and content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
        raise ValueError(f"This URL returned unsupported content type: {content_type}")

    if content_type == "text/plain":
        text = _clean_text(response.text)
        title = None
    else:
        text, title = _extract_html_text(response.text)

    if len(text) < 80:
        raise ValueError("The source did not contain enough readable text to analyze.")

    return ExtractedSource(
        text=text[:MAX_SOURCE_CHARS],
        title=title,
        method="web_extract",
        content_type=content_type or None,
    )


def _sentence_candidates(text: str) -> list[tuple[int, str]]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", normalized)
    candidates: list[tuple[int, str]] = []
    cursor = 0

    for part in parts:
        sentence = part.strip(" \t\n-–—•")
        if 45 <= len(sentence) <= 360:
            idx = normalized.find(sentence, cursor)
            if idx < 0:
                idx = cursor
            candidates.append((idx, sentence))
            cursor = idx + len(sentence)

    if candidates:
        return candidates

    # Fallback for transcripts without sentence punctuation.
    words = normalized.split()
    chunks: list[tuple[int, str]] = []
    for i in range(0, len(words), 28):
        chunk = " ".join(words[i : i + 36]).strip()
        if len(chunk) >= 45:
            chunks.append((i, chunk))
    return chunks


def _score_sentence(sentence: str, position: int, total_chars: int) -> float:
    lower = sentence.lower()
    score = 56.0
    score += min(len(sentence) / 18.0, 14.0)

    signal_terms = (
        "because",
        "but",
        "however",
        "revealed",
        "reveals",
        "announced",
        "announces",
        "first",
        "new",
        "will",
        "says",
        "said",
        "according",
        "why",
        "how",
        "change",
        "changed",
        "difference",
        "important",
    )
    score += min(sum(1 for term in signal_terms if term in lower) * 2.4, 12.0)

    if re.search(r"\d", sentence):
        score += 4.5
    if '"' in sentence or "“" in sentence or "”" in sentence:
        score += 3.0
    if re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", sentence):
        score += 4.0

    # Slight preference for earlier source material without overwhelming substance.
    if total_chars > 0:
        relative = min(max(position / total_chars, 0.0), 1.0)
        score += (1.0 - relative) * 3.0

    return min(round(score, 1), 96.0)


def _angle_title(sentence: str) -> str:
    value = sentence.strip().strip('"“”')
    value = re.sub(r"\s+", " ", value)
    if len(value) <= 92:
        return value.rstrip(".?!")

    words = value.split()
    title = " ".join(words[:14]).rstrip(",;:.!?")
    return title + "…"


def build_story_angles(text: str, limit: int = 3) -> list[dict]:
    candidates = _sentence_candidates(text)
    if not candidates:
        return []

    ranked = sorted(
        (
            {
                "position": position,
                "sentence": sentence,
                "score": _score_sentence(sentence, position, len(text)),
            }
            for position, sentence in candidates
        ),
        key=lambda item: item["score"],
        reverse=True,
    )

    selected: list[dict] = []
    seen_tokens: list[set[str]] = []

    for item in ranked:
        tokens = {
            token
            for token in re.findall(r"[a-z0-9']+", item["sentence"].lower())
            if len(token) > 3
        }
        if any(tokens and len(tokens & prior) / max(len(tokens), 1) > 0.72 for prior in seen_tokens):
            continue

        rank = len(selected) + 1
        selected.append(
            {
                "rank": rank,
                "score": item["score"],
                "title": _angle_title(item["sentence"]),
                "claim": item["sentence"],
                "excerpt": item["sentence"],
                "location": f"Source text · character {item['position']:,}",
                "signal": "High signal" if rank == 1 else ("Strong" if rank == 2 else "Candidate"),
                "verification_level": "direct_extract",
            }
        )
        seen_tokens.append(tokens)
        if len(selected) >= limit:
            break

    return selected
