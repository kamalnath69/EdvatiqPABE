from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..db import db
from ..schemas import CoachReviewIn, CoachReviewOut
from ..utils import dependencies
from ..utils.roles import has_any_role, normalize_role
from ..utils.workspace import clean_doc, list_collection, log_workspace_event, make_id, require_student_access

router = APIRouter(prefix="/coach-reviews", tags=["coach_reviews"])


def _can_access_review(current_user, review: dict) -> bool:
    if normalize_role(current_user.role) == "admin":
        return True
    if review.get("student") == current_user.username:
        return True
    if review.get("reviewer") == current_user.username:
        return True
    return has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]) and review.get("academy_id") == current_user.academy_id


@router.get("/", response_model=list[CoachReviewOut])
async def list_reviews(current_user=Depends(dependencies.get_current_active_user)):
    role = normalize_role(current_user.role)
    query = {}
    if role == "student":
        query = {"student": current_user.username}
    elif has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]):
        query = {"academy_id": current_user.academy_id}
    return await list_collection("coach_reviews", query, sort=[("updated_at", -1)])


@router.post("/", response_model=CoachReviewOut)
async def create_review(payload: CoachReviewIn, current_user=Depends(dependencies.get_current_active_user)):
    if not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")
    student = await require_student_access(payload.student, current_user)
    now = datetime.utcnow().timestamp()
    doc = {
        "id": make_id("review"),
        **payload.dict(),
        "reviewer": current_user.username,
        "academy_id": student.get("academy_id"),
        "created_at": now,
        "updated_at": now,
    }
    await db.coach_reviews.insert_one(doc)
    await db.sessions.update_many(
        {"id": {"$in": [payload.primary_session_id, payload.comparison_session_id]}},
        {"$set": {"review_status": payload.approval_state or "draft", "last_reviewed_at": now, "last_reviewed_by": current_user.username}},
    )
    await log_workspace_event(
        current_user,
        action="coach_review.created",
        entity_type="coach_review",
        entity_id=doc["id"],
        summary=f"Created coach review {payload.title}.",
        target_user=payload.student,
        academy_id=student.get("academy_id"),
        notify_users=[payload.student],
    )
    return doc


@router.put("/{review_id}", response_model=CoachReviewOut)
async def update_review(review_id: str, payload: CoachReviewIn, current_user=Depends(dependencies.get_current_active_user)):
    review = await db.coach_reviews.find_one({"id": review_id})
    if not review:
        raise HTTPException(status_code=404, detail="Coach review not found")
    if not _can_access_review(current_user, review):
        raise HTTPException(status_code=403, detail="Cannot edit coach review")
    updates = {**payload.dict(), "updated_at": datetime.utcnow().timestamp()}
    await db.coach_reviews.update_one({"id": review_id}, {"$set": updates})
    updated = clean_doc(await db.coach_reviews.find_one({"id": review_id}))
    await log_workspace_event(
        current_user,
        action="coach_review.updated",
        entity_type="coach_review",
        entity_id=review_id,
        summary=f"Updated coach review {updated.get('title', review_id)}.",
        target_user=updated.get("student"),
        academy_id=updated.get("academy_id"),
        notify_users=[updated.get("student")] if updated.get("student") else None,
    )
    return updated
