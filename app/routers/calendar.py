from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..db import db
from ..schemas import CalendarEventIn, CalendarEventOut
from ..utils import dependencies
from ..utils.roles import has_any_role, normalize_role
from ..utils.workspace import clean_doc, list_collection, log_workspace_event, make_id, require_student_access

router = APIRouter(prefix="/calendar", tags=["calendar"])


def _can_access_event(current_user, event: dict) -> bool:
    if normalize_role(current_user.role) == "admin":
        return True
    if event.get("owner") == current_user.username:
        return True
    if event.get("student") == current_user.username:
        return True
    attendees = event.get("attendees") or []
    if current_user.username in attendees:
        return True
    return has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]) and event.get("academy_id") == current_user.academy_id


@router.get("/", response_model=list[CalendarEventOut])
async def list_events(current_user=Depends(dependencies.get_current_active_user)):
    role = normalize_role(current_user.role)
    query = {}
    if role == "student":
        query = {"$or": [{"student": current_user.username}, {"attendees": current_user.username}, {"owner": current_user.username}]}
    elif has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]):
        query = {"academy_id": current_user.academy_id}
    return await list_collection("calendar_events", query, sort=[("start_at", 1)])


@router.post("/", response_model=CalendarEventOut)
async def create_event(payload: CalendarEventIn, current_user=Depends(dependencies.get_current_active_user)):
    academy_id = current_user.academy_id
    if payload.student:
        student = await require_student_access(payload.student, current_user)
        academy_id = student.get("academy_id")
    elif not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        academy_id = current_user.academy_id
    now = datetime.utcnow().timestamp()
    doc = {
        "id": make_id("cal"),
        **payload.dict(),
        "owner": current_user.username,
        "academy_id": academy_id,
        "created_at": now,
        "updated_at": now,
    }
    await db.calendar_events.insert_one(doc)
    notify = [payload.student] if payload.student else list(set((payload.attendees or []) + [current_user.username]))
    await log_workspace_event(
        current_user,
        action="calendar.created",
        entity_type="calendar",
        entity_id=doc["id"],
        summary=f"Scheduled {payload.title}.",
        target_user=payload.student,
        academy_id=academy_id,
        notify_users=notify,
    )
    return doc


@router.put("/{event_id}", response_model=CalendarEventOut)
async def update_event(event_id: str, payload: CalendarEventIn, current_user=Depends(dependencies.get_current_active_user)):
    event = await db.calendar_events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    if not _can_access_event(current_user, event):
        raise HTTPException(status_code=403, detail="Cannot edit event")
    updates = {**payload.dict(), "updated_at": datetime.utcnow().timestamp()}
    await db.calendar_events.update_one({"id": event_id}, {"$set": updates})
    updated = clean_doc(await db.calendar_events.find_one({"id": event_id}))
    await log_workspace_event(
        current_user,
        action="calendar.updated",
        entity_type="calendar",
        entity_id=event_id,
        summary=f"Updated calendar item {updated.get('title', event_id)}.",
        target_user=updated.get("student"),
        academy_id=updated.get("academy_id"),
        notify_users=list(set((updated.get("attendees") or []) + ([updated.get("student")] if updated.get("student") else []))),
    )
    return updated
