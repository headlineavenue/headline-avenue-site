from fastapi import APIRouter, Depends

from ..schemas import SourceGuardCheckIn, SourceGuardCheckOut
from ..security import WorkspaceContext, get_workspace_context
from ..services.sourceguard import check_claim

router = APIRouter(prefix="/sourceguard", tags=["sourceguard"])


@router.post("/check", response_model=SourceGuardCheckOut)
def sourceguard_check(
    payload: SourceGuardCheckIn,
    workspace: WorkspaceContext = Depends(get_workspace_context),
) -> SourceGuardCheckOut:
    # The check itself is stateless, but authentication prevents the production
    # verification endpoint from becoming an unauthenticated public compute API.
    _ = workspace
    return check_claim(payload.claim, payload.excerpt)
