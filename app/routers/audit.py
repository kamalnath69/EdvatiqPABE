from fastapi import APIRouter, Depends, HTTPException

from ..schemas import AuditLogOut
from ..utils import dependencies
from ..utils.roles import has_any_role, normalize_role
from ..utils.workspace import list_collection

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/", response_model=list[AuditLogOut])
async def list_audit_logs(
    actor: str | None = None,
    entity_type: str | None = None,
    action: str | None = None,
    current_user=Depends(dependencies.get_current_active_user),
):
    if not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")
    query = {}
    if normalize_role(current_user.role) != "admin":
        query["academy_id"] = current_user.academy_id
    if actor:
        query["actor"] = actor
    if entity_type:
        query["entity_type"] = entity_type
    if action:
        query["action"] = action
    return await list_collection("audit_logs", query, sort=[("created_at", -1)])
