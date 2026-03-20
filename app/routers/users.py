from datetime import datetime
from fastapi import APIRouter, Body, Depends, HTTPException
from typing import List
from ..schemas import UserIn, UserOut, UserInDB, UserProfileUpdate
from ..utils import auth, dependencies
from ..utils.auth import get_password_hash
from ..utils.notifications import send_onboarding_emails
from ..utils.roles import has_any_role, normalize_role
from ..utils.default_rules import build_default_rule_entry, normalize_sport
from ..utils.workspace import log_workspace_event
from ..db import db

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/", response_model=UserOut)
async def create_user(user: UserIn, current_user: UserInDB = Depends(dependencies.get_current_active_admin)):
    existing = await auth.get_user(user.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")
    role = normalize_role(user.role)
    if role not in ["admin", "academy_admin"]:
        raise HTTPException(status_code=400, detail="Admin can create only admin or academyAdmin users here")
    if role == "academy_admin":
        if not user.academy_id:
            raise HTTPException(status_code=400, detail="academy_id is required for academy admin")
        academy = await db.academies.find_one({"academy_id": user.academy_id})
        if not academy:
            raise HTTPException(status_code=404, detail="Academy not found")
    user_dict = user.dict()
    try:
        user_dict["hashed_password"] = get_password_hash(user_dict.pop("password"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    user_dict["role"] = role
    email_verified = False if user_dict.get("email") else True
    user_dict["email_verified"] = email_verified
    user_dict["email_verified_at"] = datetime.utcnow().timestamp() if email_verified else None
    await auth.create_user(user_dict)
    await log_workspace_event(
        current_user,
        action="user.created",
        entity_type="user",
        entity_id=user.username,
        summary=f"Created {role} account {user.username}.",
        target_user=user.username,
        academy_id=user.academy_id,
    )
    try:
        await send_onboarding_emails(user_dict)
    except Exception:
        pass
    return UserOut(**user_dict)

@router.get("/", response_model=List[UserOut])
async def list_users(current_user: UserInDB = Depends(dependencies.get_current_active_admin)):
    users = await auth.list_users()
    return [UserOut(**u) for u in users]


@router.get("/students", response_model=List[UserOut])
async def list_students(current_user: UserInDB = Depends(dependencies.get_current_active_user)):
    query = {"role": "student"}
    if has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]):
        query["academy_id"] = current_user.academy_id
    elif not has_any_role(current_user.role, ["admin"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")

    results = []
    cursor = db.users.find(query)
    async for user in cursor:
        results.append(UserOut(**user))
    return results

@router.get("/{username}", response_model=UserOut)
async def get_user(username: str, current_user: UserInDB = Depends(dependencies.get_current_active_admin)):
    user = await auth.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(**user)

@router.delete("/{username}")
async def delete_user(username: str, current_user: UserInDB = Depends(dependencies.get_current_active_admin)):
    await auth.delete_user(username)
    return {"detail": "deleted"}


@router.patch("/{username}/assign_sport")
async def assign_sport(username: str, sport: str, current_user: UserInDB = Depends(dependencies.get_current_active_user)):
    # only staff/academy admin/admin can assign sport to student
    if not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")
    student = await auth.get_user(username)
    if not student or normalize_role(student.role) != "student":
        raise HTTPException(status_code=404, detail="Student not found")
    if has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]) and current_user.academy_id != student.academy_id:
        raise HTTPException(status_code=403, detail="Cannot assign sport outside academy")
    sport_name = normalize_sport(sport)
    sport_rules = getattr(student, "sport_rules", None) or {}
    updates = {"assigned_sport": sport_name}
    if sport_name not in sport_rules:
        updates[f"sport_rules.{sport_name}"] = build_default_rule_entry(
            sport_name, getattr(student, "angle_measurements", None)
        )
    await db.users.update_one({"username": username}, {"$set": updates})
    return {"username": username, "assigned_sport": sport_name}


@router.get("/me/profile", response_model=UserOut)
async def get_my_profile(current_user: UserInDB = Depends(dependencies.get_current_active_user)):
    return UserOut(**current_user.dict())


@router.patch("/me/profile", response_model=UserOut)
async def update_my_profile(
    payload: UserProfileUpdate,
    current_user: UserInDB = Depends(dependencies.get_current_active_user),
):
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if not updates:
        return UserOut(**current_user.dict())

    await db.users.update_one({"username": current_user.username}, {"$set": updates})
    updated = await auth.get_user(current_user.username)
    await log_workspace_event(
        current_user,
        action="profile.updated",
        entity_type="user_profile",
        entity_id=current_user.username,
        summary="Updated profile information.",
        target_user=current_user.username,
        notify_users=[current_user.username],
    )
    return UserOut(**updated.dict())


@router.patch("/{username}/angle_measurements")
async def update_student_angle_measurements(
    username: str,
    payload: dict = Body(...),
    current_user: UserInDB = Depends(dependencies.get_current_active_user),
):
    if not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")

    student = await auth.get_user(username)
    if not student or normalize_role(student.role) != "student":
        raise HTTPException(status_code=404, detail="Student not found")

    if has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]) and current_user.academy_id != student.academy_id:
        raise HTTPException(status_code=403, detail="Cannot modify student outside academy")

    await db.users.update_one({"username": username}, {"$set": {"angle_measurements": payload}})
    await log_workspace_event(
        current_user,
        action="student.angles.updated",
        entity_type="user_profile",
        entity_id=username,
        summary=f"Updated baseline targets for {username}.",
        target_user=username,
        academy_id=student.academy_id,
        notify_users=[username],
    )
    return {"username": username, "angle_measurements": payload}
