from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..db import db
from ..schemas import TrainingPlanIn, TrainingPlanOut, TrainingPlanProgressIn
from ..utils import dependencies
from ..utils.roles import has_any_role, normalize_role
from ..utils.workspace import clean_doc, list_collection, log_workspace_event, make_id, require_student_access

router = APIRouter(prefix="/training-plans", tags=["training_plans"])


def _can_access_plan(current_user, plan: dict) -> bool:
    if normalize_role(current_user.role) == "admin":
        return True
    if plan.get("student") == current_user.username or plan.get("owner") == current_user.username:
        return True
    return has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]) and plan.get("academy_id") == current_user.academy_id


@router.get("/", response_model=list[TrainingPlanOut])
async def list_training_plans(current_user=Depends(dependencies.get_current_active_user)):
    role = normalize_role(current_user.role)
    query = {}
    if role == "student":
        query = {"student": current_user.username}
    elif has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]):
        query = {"academy_id": current_user.academy_id}
    return await list_collection("training_plans", query, sort=[("updated_at", -1)])


@router.post("/", response_model=TrainingPlanOut)
async def create_training_plan(payload: TrainingPlanIn, current_user=Depends(dependencies.get_current_active_user)):
    role = normalize_role(current_user.role)
    if not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff", "student"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")
    target_student = payload.student or current_user.username
    if role == "student" and target_student != current_user.username:
        raise HTTPException(status_code=403, detail="Students can only create their own training plans")
    student = await require_student_access(target_student, current_user)
    now = datetime.utcnow().timestamp()
    doc = {
        "id": make_id("plan"),
        **payload.dict(),
        "student": target_student,
        "owner": current_user.username,
        "academy_id": student.get("academy_id"),
        "created_at": now,
        "updated_at": now,
    }
    await db.training_plans.insert_one(doc)
    await log_workspace_event(
        current_user,
        action="training_plan.created",
        entity_type="training_plan",
        entity_id=doc["id"],
        summary=f"Assigned training plan {payload.title}.",
        target_user=target_student,
        academy_id=student.get("academy_id"),
        notify_users=[target_student],
    )
    return doc


@router.put("/{plan_id}", response_model=TrainingPlanOut)
async def update_training_plan(plan_id: str, payload: TrainingPlanIn, current_user=Depends(dependencies.get_current_active_user)):
    plan = await db.training_plans.find_one({"id": plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail="Training plan not found")
    if not _can_access_plan(current_user, plan):
        raise HTTPException(status_code=403, detail="Cannot edit training plan")
    if normalize_role(current_user.role) == "student" and plan.get("student") != current_user.username:
        raise HTTPException(status_code=403, detail="Students can only edit their own training plans")
    doc = {**payload.dict(), "updated_at": datetime.utcnow().timestamp()}
    await db.training_plans.update_one({"id": plan_id}, {"$set": doc})
    updated = clean_doc(await db.training_plans.find_one({"id": plan_id}))
    await log_workspace_event(
        current_user,
        action="training_plan.updated",
        entity_type="training_plan",
        entity_id=plan_id,
        summary=f"Updated training plan {updated.get('title', plan_id)}.",
        target_user=updated.get("student"),
        academy_id=updated.get("academy_id"),
        notify_users=[updated.get("student")] if updated.get("student") else None,
    )
    return updated


@router.post("/{plan_id}/progress", response_model=TrainingPlanOut)
async def update_training_plan_progress(plan_id: str, payload: TrainingPlanProgressIn, current_user=Depends(dependencies.get_current_active_user)):
    plan = await db.training_plans.find_one({"id": plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail="Training plan not found")
    if not _can_access_plan(current_user, plan):
        raise HTTPException(status_code=403, detail="Cannot update training plan")
    updates = {"updated_at": datetime.utcnow().timestamp()}
    for key, value in payload.dict().items():
        if value is not None:
            updates[key] = value
    await db.training_plans.update_one({"id": plan_id}, {"$set": updates})
    updated = clean_doc(await db.training_plans.find_one({"id": plan_id}))
    notify_users = []
    if normalize_role(current_user.role) == "student" and plan.get("owner"):
        notify_users.append(plan["owner"])
    elif plan.get("student"):
        notify_users.append(plan["student"])
    await log_workspace_event(
        current_user,
        action="training_plan.progress_updated",
        entity_type="training_plan",
        entity_id=plan_id,
        summary=f"Updated progress for {updated.get('title', plan_id)}.",
        target_user=updated.get("student"),
        academy_id=updated.get("academy_id"),
        notify_users=notify_users,
    )
    return updated
