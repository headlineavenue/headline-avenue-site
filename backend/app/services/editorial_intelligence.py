from __future__ import annotations

import re
from typing import Any

SAFE_FRAME_WORDS = {
    "how", "why", "what", "the", "a", "an", "this", "that", "here", "heres",
    "source", "says", "about", "inside", "behind", "story", "angle", "explained",
    "explains", "according", "to", "from", "in", "on", "and", "or", "of", "for",
    "with", "without", "into", "its", "their", "your", "our", "one",
}

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "that", "this",
    "these", "those", "to", "of", "for", "from", "in", "on", "at", "by", "with",
    "without", "as", "is", "was", "were", "be", "been", "being", "are", "am",
    "it", "its", "they", "their", "them", "we", "our", "us", "you", "your",
    "he", "his", "she", "her", "i", "my", "me", "do", "does", "did", "can",
    "could", "would", "should", "will", "may", "might", "must", "have", "has",
    "had", "not", "no", "yes", "so", "because", "actually", "very", "more",
}

RISKY_EDITORIAL_TERMS = {
    "bombshell", "shocking", "secret", "exposed", "exposes", "slam", "slams",
    "destroy", "destroys", "admits", "confirms", "proves", "exclusive",
    "breaking", "scandal", "lie", "lies", "fraud", "abuse", "abused",
}

MODE_LABELS = {
    "balanced": "Balanced",
    "breaking": "Breaking-style",
    "explainer": "Explainer",
    "social": "Social",
}


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().strip('"“”')


def _capitalize(value: str) -> str:
    value = _clean(value)
    return value[:1].upper() + value[1:] if value else value


def _lower_first(value: str) -> str:
    value = _clean(value)
    if not value:
        return value
    if len(value) > 1 and value[:2].isupper():
        return value
    return value[:1].lower() + value[1:]


def _strip_discourse(value: str) -> str:
    value = _clean(value)
    value = re.sub(r"^(yes|no|well|so|and)\s*[,.:;-]?\s+", "", value, flags=re.I)
    value = re.sub(r"^(originally|initially)\s*,\s*", "", value, flags=re.I)
    return _capitalize(value)


def _trim(value: str, limit: int = 108) -> str:
    value = _clean(value).rstrip(".?!")
    if len(value) <= limit:
        return value

    cut = value[: limit + 1]
    candidates = [
        cut.rfind(", "),
        cut.rfind("; "),
        cut.rfind(" — "),
        cut.rfind(": "),
        cut.rfind(" "),
    ]
    index = max(candidates)
    if index >= max(36, int(limit * 0.58)):
        cut = cut[:index]
    return cut.rstrip(",;: -–—") + "…"


def _balanced(title: str, evidence: str) -> str:
    return _trim(_strip_discourse(title or evidence), 108)


def _breaking(title: str, evidence: str) -> str:
    evidence = _clean(evidence)

    because = re.search(r"^(.{24,100}?)\s+because\s+(.+)$", evidence, re.I)
    if because:
        return _trim(_strip_discourse(because.group(1)), 82)

    contrast = re.search(
        r"\bbut\s+(?:we\s+)?(?:realized|found|learned|discovered)\s+(?:that\s+)?(.+)$",
        evidence,
        re.I,
    )
    if contrast:
        return _trim(_capitalize(contrast.group(1)), 88)

    becomes = re.search(r"^(.{10,65}?)\s+(?:could|can)\s+become\s+(.+)$", evidence, re.I)
    if becomes:
        return _trim(_capitalize(becomes.group(1)) + ": " + becomes.group(2), 88)

    value = _strip_discourse(title or evidence)
    value = re.sub(r"^That meant\s+", "", value, flags=re.I)
    return _trim(_capitalize(value), 78)


def _explainer(title: str, evidence: str) -> str:
    evidence = _clean(evidence)

    because = re.search(r"^(.{18,100}?)\s+because\s+(.+)$", evidence, re.I)
    if because:
        core = _strip_discourse(because.group(1))
        return _trim("Why " + _lower_first(core), 94)

    base = _strip_discourse(title or evidence)
    base = re.sub(r"^That meant\s+", "", base, flags=re.I)
    return _trim("How " + _lower_first(base), 100)


def _social(title: str, evidence: str) -> str:
    evidence = _clean(evidence)

    becomes = re.search(r"^(.{10,65}?)\s+(?:could|can)\s+become\s+(.+)$", evidence, re.I)
    if becomes:
        subject = _capitalize(becomes.group(1))
        rest = becomes.group(2).rstrip(".")
        items = [
            re.sub(r"^(?:and|or|a|an|the)\s+", "", part.strip(), flags=re.I)
            for part in re.split(r",\s*|\s+or\s+", rest)
            if part.strip()
        ]
        items = [_capitalize(item) for item in items if item]
        if len(items) >= 3:
            return _trim(". ".join(items[:4]) + ". " + subject, 96)

    because = re.search(r"^(.{18,90}?)\s+because\s+(.+)$", evidence, re.I)
    if because:
        return _trim(_strip_discourse(because.group(1)) + ". Here's why", 82)

    value = _strip_discourse(title or evidence)
    value = re.sub(r"^That meant\s+", "", value, flags=re.I)
    return _trim(_capitalize(value), 70)


def _hook_from_headline(headline: str, mode: str) -> str:
    value = headline.rstrip(".")
    if mode in {"breaking", "social"}:
        return _trim(value.upper(), 66)
    return _trim(value, 72)


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9']+", value.lower())
        if len(token) > 2 and token not in STOP_WORDS
    }


def sourceguard_headline(headline: str, evidence: str) -> dict[str, Any]:
    headline_lower = headline.lower()
    evidence_lower = evidence.lower()

    reasons: list[str] = []
    needs_review = False

    headline_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", headline))
    evidence_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", evidence))
    invented_numbers = headline_numbers - evidence_numbers
    if invented_numbers:
        needs_review = True
        reasons.append("Headline introduces a number that is not present in the evidence.")

    risky = sorted(term for term in RISKY_EDITORIAL_TERMS if term in headline_lower and term not in evidence_lower)
    if risky:
        needs_review = True
        reasons.append("Headline adds loaded wording not found in the source: " + ", ".join(risky) + ".")

    evidence_tokens = _tokens(evidence)
    headline_tokens = _tokens(headline)
    new_tokens = {
        token
        for token in headline_tokens - evidence_tokens
        if token not in SAFE_FRAME_WORDS
    }

    factual_count = max(len(headline_tokens), 1)
    overlap = len(headline_tokens & evidence_tokens)
    grounding_score = round((overlap / factual_count) * 100)

    if len(new_tokens) > 2:
        needs_review = True
        reasons.append(
            "Headline adds several content words that are not present in the selected evidence: "
            + ", ".join(sorted(new_tokens)[:6])
            + "."
        )

    if not reasons:
        reasons.append("Headline wording stays within the selected evidence and safe editorial framing.")

    return {
        "status": "needs_review" if needs_review else "source_aligned",
        "verification_level": "lexical_grounding_v1",
        "grounding_score": grounding_score,
        "reasons": reasons,
    }


def build_editorial_variants(angle: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = _clean(angle.get("excerpt") or angle.get("claim") or "")
    base_title = _clean(angle.get("title") or angle.get("claim") or evidence)

    generated = {
        "balanced": _balanced(base_title, evidence),
        "breaking": _breaking(base_title, evidence),
        "explainer": _explainer(base_title, evidence),
        "social": _social(base_title, evidence),
    }

    variants: list[dict[str, Any]] = []
    seen: set[str] = set()

    for mode in ("balanced", "breaking", "explainer", "social"):
        headline = _clean(generated[mode])
        if not headline:
            continue
        key = headline.lower()
        if key in seen:
            continue
        seen.add(key)

        guard = sourceguard_headline(headline, evidence)
        variants.append(
            {
                "mode": mode,
                "label": MODE_LABELS[mode],
                "headline": headline,
                "hook": _hook_from_headline(headline, mode),
                "sourceguard_status": guard["status"],
                "verification_level": guard["verification_level"],
                "grounding_score": guard["grounding_score"],
                "reasons": guard["reasons"],
            }
        )

    return variants
