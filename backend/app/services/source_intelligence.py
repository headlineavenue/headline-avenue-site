from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (compatible; HeadlineAvenueBot/0.2; "
    "+https://headlineavenue.github.io/headline-avenue-site/)"
)
MAX_SOURCE_CHARS = 120_000

QUESTION_SPEAKERS = {"interviewer", "host", "reporter", "moderator", "question"}
ANSWER_SPEAKERS = {"guest", "answer"}


@dataclass
class ExtractedSource:
    text: str
    title: str | None
    method: str
    content_type: str | None = None


@dataclass
class SentenceCandidate:
    position: int
    sentence: str
    speaker: str | None = None


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


def _speaker_segments(text: str) -> list[tuple[int, str, str | None]]:
    """Split transcript-like text into speaker turns while preserving source positions."""
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    speaker_re = re.compile(
        r"(?i)(?<!\w)(interviewer|guest|host|reporter|moderator|question|answer|speaker\s*\d*)\s*:\s*"
    )
    matches = list(speaker_re.finditer(normalized))
    if not matches:
        return [(0, normalized, None)]

    segments: list[tuple[int, str, str | None]] = []

    # Preserve meaningful source text that appears before the first speaker label,
    # but ignore explicit development/test preambles.
    preamble = normalized[: matches[0].start()].strip(" -–—")
    if preamble and "test transcript" not in preamble.lower() and len(preamble) >= 45:
        segments.append((0, preamble, None))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        body = normalized[match.end() : end].strip()
        speaker = re.sub(r"\s+", " ", match.group(1).lower()).strip()
        if body:
            segments.append((match.end(), body, speaker))

    return segments


def _split_segment(position: int, body: str, speaker: str | None) -> list[SentenceCandidate]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", body)
    candidates: list[SentenceCandidate] = []
    cursor = 0

    for part in parts:
        sentence = part.strip(" \t\n-–—•")
        local_index = body.find(sentence, cursor) if sentence else -1
        if local_index < 0:
            local_index = cursor
        cursor = local_index + len(sentence)

        if not sentence:
            continue
        if sentence.endswith("?"):
            continue
        if speaker in QUESTION_SPEAKERS:
            continue
        if sentence.lower().startswith("test transcript"):
            continue
        if 45 <= len(sentence) <= 420:
            candidates.append(
                SentenceCandidate(
                    position=position + local_index,
                    sentence=sentence,
                    speaker=speaker,
                )
            )

    return candidates


def _sentence_candidates(text: str) -> list[SentenceCandidate]:
    candidates: list[SentenceCandidate] = []
    for position, body, speaker in _speaker_segments(text):
        candidates.extend(_split_segment(position, body, speaker))

    if candidates:
        return candidates

    # Fallback for unpunctuated transcripts or plain text.
    normalized = re.sub(r"\s+", " ", text).strip()
    words = normalized.split()
    chunks: list[SentenceCandidate] = []
    for i in range(0, len(words), 28):
        chunk = " ".join(words[i : i + 36]).strip()
        if len(chunk) >= 45:
            chunks.append(SentenceCandidate(position=i, sentence=chunk, speaker=None))
    return chunks


def _score_sentence(candidate: SentenceCandidate, total_chars: int) -> float:
    sentence = candidate.sentence
    lower = sentence.lower()
    score = 50.0

    # Prefer statements with enough substance to express an actual editorial angle.
    score += min(len(sentence) / 17.0, 14.0)

    signal_terms = (
        "because",
        "but",
        "however",
        "realized",
        "result",
        "became",
        "faster",
        "revealed",
        "reveals",
        "announced",
        "first",
        "new",
        "changed",
        "difference",
        "important",
        "foundation",
        "evidence",
        "source",
        "support",
    )
    score += min(sum(1 for term in signal_terms if term in lower) * 2.2, 17.0)

    format_terms = ("video", "article", "carousel", "transcript", "document", "platform", "story")
    score += min(sum(1 for term in format_terms if term in lower) * 1.5, 7.5)

    if candidate.speaker in ANSWER_SPEAKERS:
        score += 5.5
    elif candidate.speaker:
        score += 1.0

    if re.search(r"\d", sentence):
        score += 3.0
    if '"' in sentence or "“" in sentence or "”" in sentence:
        score += 2.0
    if re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", sentence):
        score += 2.0

    # Down-rank generic setup language even when it survives speaker parsing.
    if lower.startswith(("what ", "why ", "how ", "did ", "do ", "does ", "can ", "could ")):
        score -= 18.0
    if "interviewer:" in lower or "test transcript" in lower:
        score -= 22.0

    # Slight preference for earlier source material without overwhelming substance.
    if total_chars > 0:
        relative = min(max(candidate.position / total_chars, 0.0), 1.0)
        score += (1.0 - relative) * 2.0

    return min(max(round(score, 1), 0.0), 96.0)


def _looks_like_shouting(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    if len(letters) < 12:
        return False
    return sum(1 for char in letters if char.isupper()) / len(letters) >= 0.82


def _headline_case(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if not _looks_like_shouting(value):
        return value

    small = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "from", "with", "by", "at"}
    words = value.lower().split()
    converted: list[str] = []
    for index, word in enumerate(words):
        core = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", word)
        if index and core in small:
            converted.append(word)
            continue
        match = re.match(r"^([^a-z0-9]*)(.*?)([^a-z0-9]*)$", word)
        if not match:
            converted.append(word)
            continue
        prefix, body, suffix = match.groups()
        converted.append(prefix + (body[:1].upper() + body[1:] if body else body) + suffix)
    return " ".join(converted)


def _compress_extract(value: str) -> str:
    """Shorten transcript run-ons at semantic clause boundaries without inventing facts."""
    value = re.sub(r"\s+", " ", value).strip()

    # Deepgram and other ASR providers can return long punctuation-light turns.
    # Prefer the first complete editorial thought rather than arbitrarily clipping words.
    boundary_patterns = (
        r"\s+by the time\s+",
        r"\s+i first\s+",
        r"\s+when\s+",
        r"\s+while\s+",
        r"\s+because\s+",
        r"\s+but\s+",
        r"\s+which\s+",
        r"\s+that meant\s+",
    )
    for pattern in boundary_patterns:
        match = re.search(pattern, value, re.I)
        if match and 28 <= match.start() <= 110:
            value = value[: match.start()].strip(" ,;:—-")
            break

    first_shots = re.match(
        r"^(?P<subject>.{3,48}?)\s+(?:was|were)\s+the\s+first\s+shots?\s+of\s+(?P<object>.+)$",
        value,
        re.I,
    )
    if first_shots:
        subject = _headline_case(first_shots.group("subject").strip())
        object_text = _headline_case(first_shots.group("object").strip())
        value = f"{subject}: The First Shots of {object_text}"

    first_time = re.match(
        r"^(?P<subject>.{3,60}?)\s+was\s+the\s+first\s+time\s+someone\s+had\s+(?P<body>.+)$",
        value,
        re.I,
    )
    if first_time:
        subject = _headline_case(first_time.group("subject").strip())
        body = _headline_case(first_time.group("body").strip())
        value = f"{subject} had {body}"

    return value


def _angle_title(sentence: str) -> str:
    """Produce a concise extractive headline without inventing new facts."""
    value = re.sub(r"\s+", " ", sentence.strip().strip('"“”'))
    value = re.sub(r"^(yes|no|well|so|and)\s*[,.:;-]?\s+", "", value, flags=re.I)
    value = re.sub(r"^(originally|initially)\s*,\s*", "", value, flags=re.I)

    # For explicit contrast, the second clause is often the actual newsworthy point.
    contrast = re.search(r"\bbut\s+(?:we\s+)?(?:realized|found|learned|discovered)\s+(that\s+)?(.+)$", value, re.I)
    if contrast:
        value = contrast.group(2).strip()

    value = _compress_extract(value)

    # A causal result usually makes a stronger title than the supporting explanation.
    because_index = re.search(r"\s+because\s+", value, re.I)
    if because_index and 35 <= because_index.start() <= 105:
        value = value[: because_index.start()].strip()

    value = _headline_case(value.rstrip(".?!"))
    if len(value) <= 92:
        return value

    words = value.split()
    title_words: list[str] = []
    for word in words:
        candidate = " ".join(title_words + [word])
        if len(candidate) > 88:
            break
        title_words.append(word)

    return " ".join(title_words).rstrip(",;:.!?")


def build_story_angles(text: str, limit: int = 3) -> list[dict]:
    candidates = _sentence_candidates(text)
    if not candidates:
        return []

    ranked = sorted(
        (
            {
                "position": candidate.position,
                "sentence": candidate.sentence,
                "speaker": candidate.speaker,
                "score": _score_sentence(candidate, len(text)),
            }
            for candidate in candidates
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
        if any(tokens and len(tokens & prior) / max(len(tokens), 1) > 0.64 for prior in seen_tokens):
            continue

        rank = len(selected) + 1
        score = item["score"]
        selected.append(
            {
                "rank": rank,
                "score": score,
                "title": _angle_title(item["sentence"]),
                "claim": item["sentence"],
                "excerpt": item["sentence"],
                "source_start_char": item["position"],
                "source_end_char": item["position"] + len(item["sentence"]),
                "location": f"Source text · character {item['position']:,}",
                "signal": "High signal" if score >= 82 else ("Strong" if score >= 72 else "Candidate"),
                "verification_level": "direct_extract",
            }
        )
        seen_tokens.append(tokens)
        if len(selected) >= limit:
            break

    return selected
