from fastapi import APIRouter

from ..schemas import SourceGuardCheckIn, SourceGuardCheckOut
from ..services.sourceguard import check_claim

router = APIRouter(prefix="/sourceguard", tags=["sourceguard"])


@router.post("/check", response_model=SourceGuardCheckOut)
def sourceguard_check(payload: SourceGuardCheckIn) -> SourceGuardCheckOut:
    return check_claim(payload.claim, payload.excerpt)
