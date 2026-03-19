from fastapi import APIRouter, Depends, HTTPException
from typing import List
from datetime import datetime
from ..schemas import SessionIn
from ..utils import dependencies, auth
from ..utils.roles import has_any_role, normalize_role
from ..db import db

router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.post("/", response_model=SessionIn)
async def create_session(session: SessionIn, current_user=Depends(dependencies.get_current_active_user)):
    student = await auth.get_user(session.student)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if has_any_role(current_user.role, ["student"]):
        if current_user.username != session.student:
            raise HTTPException(status_code=403, detail="Students can only save their own sessions")
    elif not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")

    if has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]) and current_user.academy_id != student.academy_id:
        raise HTTPException(status_code=403, detail="Cannot create session outside academy")
    now_ts = datetime.utcnow().timestamp()
    started_at = session.started_at if session.started_at is not None else now_ts
    ended_at = session.ended_at if session.ended_at is not None else now_ts
    if ended_at < started_at:
        ended_at = started_at
    duration_minutes = max(1, int(round((ended_at - started_at) / 60.0)))

    doc = {
        **session.dict(),
        "created_by": current_user.username,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_minutes": duration_minutes,
        "timestamp": now_ts,
    }
    await db.sessions.insert_one(doc)
    return doc

@router.get("/", response_model=List[SessionIn])
async def list_sessions(current_user=Depends(dependencies.get_current_active_user)):
    cursor = db.sessions.find()
    results = []
    async for r in cursor:
        results.append(r)
    return results

@router.get("/{student}", response_model=List[SessionIn])
async def get_sessions(student: str, current_user=Depends(dependencies.get_current_active_user)):
    if normalize_role(current_user.role) == "student" and current_user.username != student:
        raise HTTPException(status_code=403, detail="Students can only view their own sessions")
    if has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]):
        stud = await auth.get_user(student)
        if not stud or stud.academy_id != current_user.academy_id:
            raise HTTPException(status_code=403, detail="Cannot view sessions outside academy")
    cursor = db.sessions.find({"student": student})
    results = []
    async for r in cursor:
        results.append(r)
    return results
