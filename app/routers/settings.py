from fastapi import APIRouter, Depends, HTTPException

from ..db import db
from ..schemas import AcademySettingsIn, UserSettingsIn, WorkspaceSettingsOut
from ..utils import dependencies
from ..utils.roles import has_any_role, normalize_role
from ..utils.workspace import (
    build_default_academy_settings,
    build_default_user_settings,
    clean_doc,
    log_workspace_event,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/me", response_model=WorkspaceSettingsOut)
async def get_my_settings(current_user=Depends(dependencies.get_current_active_user)):
    user_doc = await db.user_settings.find_one({"username": current_user.username})
    academy_doc = None
    if current_user.academy_id:
        academy_doc = await db.academy_settings.find_one({"academy_id": current_user.academy_id})
    return WorkspaceSettingsOut(
        user=build_default_user_settings(clean_doc(user_doc)),
        academy=build_default_academy_settings(clean_doc(academy_doc), current_user.academy_id),
    )


@router.put("/me", response_model=WorkspaceSettingsOut)
async def update_my_settings(payload: UserSettingsIn, current_user=Depends(dependencies.get_current_active_user)):
    doc = {"username": current_user.username, **build_default_user_settings(payload.dict())}
    await db.user_settings.update_one({"username": current_user.username}, {"$set": doc}, upsert=True)
    await log_workspace_event(
        current_user,
        action="settings.updated",
        entity_type="settings",
        entity_id=current_user.username,
        summary="Updated personal workspace settings.",
        target_user=current_user.username,
        notify_users=[current_user.username],
    )
    academy_doc = await db.academy_settings.find_one({"academy_id": current_user.academy_id}) if current_user.academy_id else None
    return WorkspaceSettingsOut(
        user=build_default_user_settings(doc),
        academy=build_default_academy_settings(clean_doc(academy_doc), current_user.academy_id),
    )


@router.get("/academy", response_model=dict)
async def get_academy_settings(current_user=Depends(dependencies.get_current_active_user)):
    if not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")
    academy_id = current_user.academy_id
    doc = await db.academy_settings.find_one({"academy_id": academy_id}) if academy_id else None
    return build_default_academy_settings(clean_doc(doc), academy_id)


@router.put("/academy", response_model=dict)
async def update_academy_settings(payload: AcademySettingsIn, current_user=Depends(dependencies.get_current_active_user)):
    if not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")
    academy_id = payload.academy_id or current_user.academy_id
    if not academy_id:
        raise HTTPException(status_code=400, detail="academy_id is required")
    if normalize_role(current_user.role) != "admin" and academy_id != current_user.academy_id:
        raise HTTPException(status_code=403, detail="Cannot update settings outside academy")

    doc = build_default_academy_settings(payload.dict(), academy_id)
    await db.academy_settings.update_one({"academy_id": academy_id}, {"$set": doc}, upsert=True)
    await log_workspace_event(
        current_user,
        action="academy.settings.updated",
        entity_type="academy_settings",
        entity_id=academy_id,
        summary="Updated academy workspace settings.",
        academy_id=academy_id,
    )
    return doc
