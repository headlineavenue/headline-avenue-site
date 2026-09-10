from ..schemas import SourceGuardCheckOut


def check_claim(claim: str, excerpt: str | None) -> SourceGuardCheckOut:
    """
    Deterministic placeholder for the future evidence engine.

    Production SourceGuard should compare generated claims against indexed
    source evidence, timestamps, provenance, and context. This function
    intentionally does not pretend to perform semantic verification.
    """
    reasons: list[str] = []

    if not excerpt:
        reasons.append("No supporting source excerpt was supplied.")

    risky_tokens = ("%", "everyone", "nobody", "always", "never")
    if any(token in claim.lower() for token in risky_tokens):
        reasons.append("Claim contains absolute or quantified language that requires explicit evidence.")

    if reasons:
        return SourceGuardCheckOut(status="needs_review", reasons=reasons)

    return SourceGuardCheckOut(
        status="supported",
        reasons=["A source excerpt was supplied; semantic verification is not implemented yet."],
    )
