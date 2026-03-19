from fastapi import APIRouter, Depends, HTTPException

from ..db import db
from ..schemas import NotificationOut
from ..utils import dependencies
from ..utils.roles import has_any_role
from ..utils.workspace import clean_doc, list_collection

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=list[NotificationOut])
async def list_notifications(unread_only: bool = False, current_user=Depends(dependencies.get_current_active_user)):
    query = {"target_user": current_user.username}
    if unread_only:
        query["read"] = False
    return await list_collection("notifications", query, sort=[("created_at", -1)])


@router.post("/{notification_id}/read")
async def mark_notification_read(notification_id: str, current_user=Depends(dependencies.get_current_active_user)):
    doc = await db.notifications.find_one({"id": notification_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Notification not found")
    if doc.get("target_user") != current_user.username and not has_any_role(current_user.role, ["admin"]):
        raise HTTPException(status_code=403, detail="Cannot update notification")
    await db.notifications.update_one({"id": notification_id}, {"$set": {"read": True}})
    updated = await db.notifications.find_one({"id": notification_id})
    return clean_doc(updated)


@router.post("/read-all")
async def mark_all_notifications_read(current_user=Depends(dependencies.get_current_active_user)):
    await db.notifications.update_many({"target_user": current_user.username, "read": False}, {"$set": {"read": True}})
    return {"detail": "Notifications marked as read."}
