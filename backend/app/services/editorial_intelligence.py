from __future__ import annotations

import re
from typing import Any

SAFE_FRAME_WORDS = {
    "how", "why", "what", "the", "a", "an", "this", "that", "here", "heres", "source", "says", "about",
    "inside", "behind", "story", "angle", "explained", "explains", "according", "to", "from", "in", "on",
    "and", "or", "of", "for", "with", "without", "into", "its", "their", "your", "our", "one", "same",
    "multiple", "format", "formats", "across", "beyond", "keeps", "keeping", "stay", "stays", "less",
    "more", "via", "turn", "turns", "turning", "every", "each", "piece", "reporting", "editorial",
    "content", "team", "teams", "attached", "trail", "source", "short", "longer",
}

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "that", "this", "these", "those", "to", "of",
    "for", "from", "in", "on", "at", "by", "with", "without", "as", "is", "was", "were", "be", "been", "being",
    "are", "am", "it", "its", "they", "their", "them", "we", "our", "us", "you", "your", "he", "his", "she",
    "her", "i", "my", "me", "do", "does", "did", "can", "could", "would", "should", "will", "may", "might",
    "must", "have", "has", "had", "not", "no", "yes", "so", "because", "actually", "very", "more",
}

RISKY_EDITORIAL_TERMS = {
    "bombshell", "shocking", "secret", "exposed", "exposes", "slam", "slams", "destroy", "destroys",
    "admits", "confirms", "proves", "exclusive", "breaking", "scandal", "lie", "lies", "fraud", "abuse", "abused",
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


def _title_case_phrase(value: str) -> str:
    small = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "from", "with"}
    words = _clean(value).split()
    return " ".join(
        word.lower() if i and word.lower() in small else word[:1].upper() + word[1:]
        for i, word in enumerate(words)
    )


def _strip_discourse(value: str) -> str:
    value = _clean(value)
    value = re.sub(r"^(yes|no|well|so|and)\s*[,.:;-]?\s+", "", value, flags=re.I)
    value = re.sub(r"^(originally|initially)\s*,\s*", "", value, flags=re.I)
    return _capitalize(value)


def _trim(value: str, limit: int = 78) -> str:
    value = _clean(value).rstrip(".?!…")
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
    if index >= max(28, int(limit * 0.56)):
        cut = cut[:index]
    return cut.rstrip(",;: -–—")


def _compact_item(value: str) -> str:
    value = _clean(value)
    value = re.sub(r"^(?:and|or)\s+", "", value, flags=re.I)
    value = re.sub(r"^(?:a|an|the)\s+", "", value, flags=re.I)
    value = re.sub(
        r"^(?:longer|short)\s+(?=(?:landscape\s+)?video\b|social\s+post\b)",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(r"^(?:original|supporting)\s+", "", value, flags=re.I)
    return _title_case_phrase(value)


def _join_items(items: list[str], conjunction: str = "and") -> str:
    items = [item for item in items if item]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    return ", ".join(items[:-1]) + f" {conjunction} {items[-1]}"


def _extract_become_pattern(evidence: str) -> tuple[str, list[str]] | None:
    match = re.search(
        r"\b(?P<subject>[a-z][a-z -]{2,48}?)\s+(?:could|can)\s+become\s+(?P<items>[^.?!]+)",
        evidence,
        re.I,
    )
    if not match:
        return None

    subject = _clean(match.group("subject"))
    subject = re.sub(
        r"^(?:but\s+)?(?:we|they|he|she|i)\s+(?:realized|found|learned|discovered)\s+(?:that\s+)?",
        "",
        subject,
        flags=re.I,
    )
    tail = re.search(
        r"((?:the\s+)?(?:same\s+)?(?:reporting|story|source|content|material|project|interview|article|video|report|piece))$",
        subject,
        re.I,
    )
    if tail:
        subject = tail.group(1)

    subject = _title_case_phrase(subject)
    raw = match.group("items")
    parts = [part for part in re.split(r",\s*|\s+or\s+|\s+and\s+", raw) if part.strip()]
    items = [_compact_item(part) for part in parts if _compact_item(part)]
    return subject, items


def _extract_origin_format(source_text: str) -> str | None:
    match = re.search(r"(?:made|designed)\s+for\s+([^,.]{4,48}?)(?:,\s*but|\s+but)", source_text, re.I)
    if not match:
        return None
    return _title_case_phrase(match.group(1))


def _extract_keep_pattern(evidence: str) -> list[str] | None:
    match = re.search(r"\bkeeping\s+(.+?)\s+connected\s+to\s+every\s+story\b", evidence, re.I)
    if not match:
        return None
    parts = [part for part in re.split(r",\s*|\s+and\s+", match.group(1)) if part.strip()]
    return [_compact_item(part) for part in parts if _compact_item(part)]


def _extract_faster_pattern(evidence: str) -> tuple[str, str] | None:
    match = re.search(
        r"\b(?P<subject>the\s+team)\s+(?:actually\s+)?became\s+faster\s+because\s+(?P<reason>.+)",
        evidence,
        re.I,
    )
    return (match.group("subject"), match.group("reason")) if match else None


def _balanced(title: str, evidence: str, source_text: str, generation: int = 0) -> str:
    become = _extract_become_pattern(evidence)
    if become:
        subject, items = become
        options = [
            f"{subject} Can Become {_join_items(items, 'or')}",
            "One Piece of Reporting Can Become Multiple Formats",
            f"From {subject} to Multiple Formats",
        ]
        return _trim(options[generation % len(options)], 78)

    keep = _extract_keep_pattern(evidence)
    if keep:
        options = [
            f"Every Story Keeps {_join_items(keep)} Connected",
            "Every Story Can Keep Its Source Trail Attached",
            "Source Evidence Can Stay Connected to Every Story",
        ]
        return _trim(options[generation % len(options)], 78)

    if _extract_faster_pattern(evidence):
        options = [
            "The Team Became Faster With Less Time Spent Searching",
            "Less Time Searching Helped the Team Move Faster",
            "The Source Trail Meant Less Searching for the Team",
        ]
        return options[generation % len(options)]

    return _trim(_strip_discourse(title or evidence), 72)


def _breaking(title: str, evidence: str, source_text: str, generation: int = 0) -> str:
    become = _extract_become_pattern(evidence)
    if become:
        subject, items = become
        origin = _extract_origin_format(source_text)
        options = []
        if origin and len(items) >= 2:
            options.extend([
                f"From {origin} to {_join_items(items, 'and')}",
                f"Beyond {origin}: {_join_items(items, 'and')}",
                f"{origin} Was Only One Format — Now the Same Reporting Spans Multiple Formats",
            ])
        else:
            options.extend([
                f"{subject}: {_join_items(items, 'and')}",
                f"Beyond One Format: {_join_items(items, 'and')}",
                f"{subject} Now Spans Multiple Formats",
            ])
        return _trim(options[generation % len(options)], 80)

    if _extract_keep_pattern(evidence):
        options = [
            "Every Story Keeps Its Source Trail Attached",
            "Source Evidence Stays Attached to the Story",
            "The Source Trail Now Travels With the Story",
        ]
        return options[generation % len(options)]

    if _extract_faster_pattern(evidence):
        options = [
            "Less Searching, Faster Team",
            "The Team Got Faster by Cutting Search Time",
            "Source Trails Cut the Time Spent Searching",
        ]
        return options[generation % len(options)]

    because = re.search(r"^(.{18,90}?)\s+because\s+(.+)$", _clean(evidence), re.I)
    if because:
        return _trim(_strip_discourse(because.group(1)), 64)

    return _trim(_strip_discourse(title or evidence), 62)


def _explainer(title: str, evidence: str, source_text: str, generation: int = 0) -> str:
    become = _extract_become_pattern(evidence)
    if become:
        subject, items = become
        options = [
            f"How {_lower_first(subject)} Can Become {_join_items(items, 'and')}",
            "How One Piece of Reporting Becomes Multiple Formats",
            f"How {_lower_first(subject)} Moves Beyond a Single Format",
        ]
        return _trim(options[generation % len(options)], 82)

    keep = _extract_keep_pattern(evidence)
    if keep:
        options = [
            f"Why {_join_items(keep)} Stay Connected to Every Story",
            "How a Source Trail Stays Attached to Every Story",
            "Why Keeping Source Evidence Connected Matters",
        ]
        return _trim(options[generation % len(options)], 82)

    if _extract_faster_pattern(evidence):
        options = [
            "Why the Team Became Faster With Less Time Spent Searching",
            "How a Source Trail Reduced the Time Spent Searching",
            "Why Less Searching Made the Team Faster",
        ]
        return options[generation % len(options)]

    base = _strip_discourse(title or evidence)
    base = re.sub(r"^That meant\s+", "", base, flags=re.I)
    return _trim("How " + _lower_first(base), 78)


def _social(title: str, evidence: str, source_text: str, generation: int = 0) -> str:
    become = _extract_become_pattern(evidence)
    if become:
        _, items = become
        origin = _extract_origin_format(source_text)
        chain = ([origin] if origin else []) + items
        options = []
        if len(chain) >= 3:
            options.append(" → ".join(chain))
        options.extend([
            "ONE PIECE OF REPORTING → MULTIPLE FORMATS",
            "VERTICAL VIDEO → LANDSCAPE → ARTICLE → CAROUSEL → SOCIAL",
        ])
        return _trim(options[generation % len(options)], 74)

    keep = _extract_keep_pattern(evidence)
    if keep:
        options = [
            "SOURCE → STORY → SOURCE TRAIL",
            "KEEP THE SOURCE ATTACHED",
            "ONE STORY. SOURCE EVIDENCE INCLUDED.",
        ]
        return options[generation % len(options)]

    if _extract_faster_pattern(evidence):
        options = [
            "LESS SEARCHING. FASTER TEAM.",
            "SOURCE TRAIL ATTACHED → LESS SEARCHING",
            "FIND THE CLAIM ONCE. KEEP THE SOURCE.",
        ]
        return options[generation % len(options)]

    return _trim(_capitalize(_strip_discourse(title or evidence)), 54)


def hook_from_headline(headline: str, mode: str) -> str:
    value = _clean(headline).rstrip(".")
    if not value:
        return ""

    if " → " in value:
        parts = [part.strip() for part in value.split(" → ") if part.strip()]
        hook = " → ".join(parts[:3])
        return hook.upper() if mode in {"breaking", "social"} else hook

    become = re.search(r"^(.+?)\s+(?:Can\s+)?Become\s+(.+)$", value, re.I)
    if become:
        subject = become.group(1)
        items = [item.strip() for item in re.split(r",\s*|\s+or\s+|\s+and\s+", become.group(2)) if item.strip()]
        if items:
            hook = f"{subject}: {', '.join(items[:2])}"
            return _trim(hook.upper() if mode in {"breaking", "social"} else hook, 58)

    if mode == "explainer":
        return _trim(value, 60)

    limit = 50 if mode == "social" else 56
    return _trim(value.upper() if mode in {"breaking", "social"} else value, limit)


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9']+", value.lower())
        if len(token) > 2 and token not in STOP_WORDS
    }


def sourceguard_headline(headline: str, evidence: str, source_text: str = "") -> dict[str, Any]:
    corpus = _clean((evidence or "") + " " + (source_text or ""))
    headline = _clean(headline)
    headline_lower = headline.lower()
    corpus_lower = corpus.lower()

    reasons: list[str] = []
    needs_review = False

    headline_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", headline))
    source_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", corpus))
    invented_numbers = headline_numbers - source_numbers
    if invented_numbers:
        needs_review = True
        reasons.append("Headline introduces a number that is not present in the source.")

    risky = sorted(
        term for term in RISKY_EDITORIAL_TERMS
        if term in headline_lower and term not in corpus_lower
    )
    if risky:
        needs_review = True
        reasons.append("Headline adds loaded wording not found in the source: " + ", ".join(risky) + ".")

    source_tokens = _tokens(corpus)
    headline_tokens = _tokens(headline)
    new_tokens = {
        token
        for token in headline_tokens - source_tokens
        if token not in SAFE_FRAME_WORDS
    }

    overlap = len(headline_tokens & source_tokens)
    grounding_score = round((overlap / max(len(headline_tokens), 1)) * 100)

    if len(new_tokens) > 1:
        needs_review = True
        reasons.append(
            "Headline adds content words not present in the indexed source: "
            + ", ".join(sorted(new_tokens)[:6])
            + "."
        )

    if grounding_score < 55 and len(headline_tokens) >= 4:
        needs_review = True
        reasons.append("Headline has low lexical overlap with the selected evidence and indexed source.")

    if len(headline) > 105:
        reasons.append("Headline is source-aligned but longer than the recommended editorial range.")

    if not reasons:
        reasons.append("Headline stays within the selected evidence and indexed source context.")

    return {
        "status": "needs_review" if needs_review else "source_aligned",
        "verification_level": "lexical_grounding_v3",
        "grounding_score": grounding_score,
        "reasons": reasons,
    }


def build_custom_editorial_variant(
    headline: str,
    mode: str,
    evidence: str,
    source_text: str = "",
) -> dict[str, Any]:
    cleaned = _clean(headline)
    guard = sourceguard_headline(cleaned, evidence, source_text)
    return {
        "mode": mode,
        "label": MODE_LABELS.get(mode, _capitalize(mode)),
        "headline": cleaned,
        "hook": hook_from_headline(cleaned, mode),
        "sourceguard_status": guard["status"],
        "verification_level": guard["verification_level"],
        "grounding_score": guard["grounding_score"],
        "reasons": guard["reasons"],
    }


def build_editorial_variants(
    angle: dict[str, Any],
    source_text: str = "",
    generation: int = 0,
) -> list[dict[str, Any]]:
    evidence = _clean(angle.get("excerpt") or angle.get("claim") or "")
    base_title = _clean(angle.get("title") or angle.get("claim") or evidence)
    full_source = _clean(source_text)

    generated = {
        "balanced": _balanced(base_title, evidence, full_source, generation),
        "breaking": _breaking(base_title, evidence, full_source, generation),
        "explainer": _explainer(base_title, evidence, full_source, generation),
        "social": _social(base_title, evidence, full_source, generation),
    }

    variants: list[dict[str, Any]] = []
    seen: set[str] = set()

    for mode in ("balanced", "breaking", "explainer", "social"):
        headline = _clean(generated[mode])
        if not headline or headline.lower() in seen:
            continue
        seen.add(headline.lower())

        variants.append(build_custom_editorial_variant(
            headline=headline,
            mode=mode,
            evidence=evidence,
            source_text=full_source,
        ))

    return variants
