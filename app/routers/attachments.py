from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..db import db
from ..schemas import AttachmentIn, AttachmentOut
from ..utils import dependencies
from ..utils.roles import has_any_role, normalize_role
from ..utils.workspace import clean_doc, list_collection, make_id

router = APIRouter(prefix="/attachments", tags=["attachments"])


def _attachment_query(current_user, entity_type: str | None = None, entity_id: str | None = None) -> dict:
    query = {}
    if normalize_role(current_user.role) != "admin":
        query["$or"] = [{"owner": current_user.username}, {"academy_id": current_user.academy_id}]
    if entity_type:
        query["entity_type"] = entity_type
    if entity_id:
        query["entity_id"] = entity_id
    return query


@router.get("/", response_model=list[AttachmentOut])
async def list_attachments(entity_type: str | None = None, entity_id: str | None = None, current_user=Depends(dependencies.get_current_active_user)):
    return await list_collection("attachments", _attachment_query(current_user, entity_type, entity_id), sort=[("updated_at", -1)])


@router.post("/", response_model=AttachmentOut)
async def create_attachment(payload: AttachmentIn, current_user=Depends(dependencies.get_current_active_user)):
    doc = {
        "id": make_id("att"),
        **payload.dict(),
        "owner": current_user.username,
        "academy_id": current_user.academy_id,
        "created_at": datetime.utcnow().timestamp(),
        "updated_at": datetime.utcnow().timestamp(),
    }
    await db.attachments.insert_one(doc)
    if payload.entity_type == "session":
        await db.sessions.update_one({"id": payload.entity_id}, {"$addToSet": {"attachment_refs": doc["id"]}})
    if payload.entity_type == "coach_review":
        await db.coach_reviews.update_one({"id": payload.entity_id}, {"$addToSet": {"attachments": doc["id"]}})
    return doc


@router.delete("/{attachment_id}")
async def delete_attachment(attachment_id: str, current_user=Depends(dependencies.get_current_active_user)):
    doc = await db.attachments.find_one({"id": attachment_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if doc.get("owner") != current_user.username and not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        raise HTTPException(status_code=403, detail="Cannot delete attachment")
    await db.attachments.delete_one({"id": attachment_id})
    return {"detail": "Attachment removed."}
