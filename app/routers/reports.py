import secrets

from fastapi import APIRouter, Depends, HTTPException

from ..db import db
from ..schemas import ReportIn, ReportOut
from ..utils import dependencies
from ..utils.roles import has_any_role, normalize_role
from ..utils.workspace import clean_doc, list_collection, log_workspace_event, make_id, require_student_access

router = APIRouter(prefix="/reports", tags=["reports"])


def _can_access_report(current_user, report: dict) -> bool:
    if normalize_role(current_user.role) == "admin":
        return True
    if report.get("owner") == current_user.username:
        return True
    if has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]) and report.get("academy_id") == current_user.academy_id:
        return True
    if normalize_role(current_user.role) == "student" and report.get("student") == current_user.username:
        return True
    return False


@router.get("/", response_model=list[ReportOut])
async def list_reports(current_user=Depends(dependencies.get_current_active_user)):
    query = {}
    role = normalize_role(current_user.role)
    if role == "student":
        query = {"$or": [{"owner": current_user.username}, {"student": current_user.username}]}
    elif has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]):
        query = {"academy_id": current_user.academy_id}
    return await list_collection("reports", query, sort=[("updated_at", -1)])


@router.post("/", response_model=ReportOut)
async def create_report(payload: ReportIn, current_user=Depends(dependencies.get_current_active_user)):
    if payload.student:
        await require_student_access(payload.student, current_user)
    now = __import__("datetime").datetime.utcnow().timestamp()
    doc = {
        "id": make_id("report"),
        **payload.dict(),
        "owner": current_user.username,
        "academy_id": current_user.academy_id,
        "org_id": getattr(current_user, "org_id", None),
        "share_token": None,
        "export_requests": [],
        "created_at": now,
        "updated_at": now,
    }
    await db.reports.insert_one(doc)
    notify = [payload.student] if payload.student and payload.student != current_user.username else [current_user.username]
    await log_workspace_event(
        current_user,
        action="report.created",
        entity_type="report",
        entity_id=doc["id"],
        summary=f"Created report {payload.title}.",
        target_user=payload.student,
        notify_users=notify,
    )
    return doc


@router.put("/{report_id}", response_model=ReportOut)
async def update_report(report_id: str, payload: ReportIn, current_user=Depends(dependencies.get_current_active_user)):
    report = await db.reports.find_one({"id": report_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not _can_access_report(current_user, report):
        raise HTTPException(status_code=403, detail="Cannot edit report")
    doc = {**payload.dict(), "updated_at": __import__("datetime").datetime.utcnow().timestamp()}
    await db.reports.update_one({"id": report_id}, {"$set": doc})
    updated = clean_doc(await db.reports.find_one({"id": report_id}))
    await log_workspace_event(
        current_user,
        action="report.updated",
        entity_type="report",
        entity_id=report_id,
        summary=f"Updated report {updated.get('title', report_id)}.",
        target_user=updated.get("student"),
        notify_users=[updated.get("student")] if updated.get("student") else [current_user.username],
    )
    return updated


@router.post("/{report_id}/share")
async def share_report(report_id: str, current_user=Depends(dependencies.get_current_active_user)):
    report = await db.reports.find_one({"id": report_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not _can_access_report(current_user, report):
        raise HTTPException(status_code=403, detail="Cannot share report")
    token = secrets.token_urlsafe(12)
    await db.reports.update_one({"id": report_id}, {"$set": {"share_token": token, "updated_at": __import__("datetime").datetime.utcnow().timestamp()}})
    return {"id": report_id, "share_token": token}


@router.post("/{report_id}/export")
async def export_report(report_id: str, current_user=Depends(dependencies.get_current_active_user)):
    report = await db.reports.find_one({"id": report_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not _can_access_report(current_user, report):
        raise HTTPException(status_code=403, detail="Cannot export report")
    export_doc = {"id": make_id("export"), "format": "pdf", "status": "ready", "requested_at": __import__("datetime").datetime.utcnow().timestamp()}
    await db.reports.update_one({"id": report_id}, {"$push": {"export_requests": export_doc}, "$set": {"updated_at": export_doc["requested_at"]}})
    return export_doc
