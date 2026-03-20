from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from ..schemas import AcademyIn, AcademyOut, UserIn, UserInDB
from ..utils import auth, dependencies
from ..utils.auth import get_password_hash
from ..utils.notifications import send_onboarding_emails
from ..utils.roles import has_any_role, normalize_role
from ..utils.default_rules import build_default_rules_map
from ..utils.workspace import log_workspace_event
from ..db import db

router = APIRouter(prefix="/academies", tags=["academies"])

@router.post("/", response_model=AcademyIn)
async def create_academy(academy: AcademyIn, current_user=Depends(dependencies.get_current_active_admin)):
    existing = await db.academies.find_one(
        {"$or": [{"academy_id": academy.academy_id}, {"name": academy.name}]}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Academy id or name already exists")
    doc = {**academy.dict(), "admins": [], "staff": [], "students": []}
    await db.academies.insert_one(doc)
    await log_workspace_event(
        current_user,
        action="academy.created",
        entity_type="academy",
        entity_id=academy.academy_id,
        summary=f"Created academy {academy.name}.",
        academy_id=academy.academy_id,
    )
    return academy

@router.get("/", response_model=List[AcademyOut])
async def list_academies(current_user=Depends(dependencies.get_current_active_user)):
    academies = []
    role = normalize_role(current_user.role)
    query = {}
    if role != "admin":
        query = {"academy_id": current_user.academy_id}

    cursor = db.academies.find(query)
    async for a in cursor:
        academies.append(
            AcademyOut(
                academy_id=a.get("academy_id", ""),
                name=a.get("name", ""),
                address=a.get("address", ""),
                city=a.get("city", ""),
                state=a.get("state", ""),
                country=a.get("country", ""),
                contact_email=a.get("contact_email"),
                contact_phone=a.get("contact_phone"),
                admins=a.get("admins", []),
                staff=a.get("staff", []),
                students=a.get("students", []),
            )
        )
    return academies

@router.delete("/{academy_id}")
async def delete_academy(academy_id: str, current_user=Depends(dependencies.get_current_active_admin)):
    await db.academies.delete_one({"academy_id": academy_id})
    return {"detail": "deleted"}

# academy user management
@router.post("/{academy_id}/admins")
async def add_academy_admin(academy_id: str, user: UserIn, current: UserInDB = Depends(dependencies.get_current_active_admin)):
    academy = await db.academies.find_one({"academy_id": academy_id})
    if not academy:
        raise HTTPException(status_code=404, detail="Academy not found")
    org = await db.orgs.find_one({"org_id": academy_id})
    plan_fields = {}
    if org:
        plan_fields = {
            "org_id": org.get("org_id"),
            "plan_code": org.get("plan_code"),
            "plan_type": "organization",
            "plan_tier": org.get("plan_tier"),
        }
    existing = await auth.get_user(user.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")
    try:
        hashed = get_password_hash(user.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    email_verified = False if user.email else True
    user_doc = {
        **user.dict(),
        "hashed_password": hashed,
        "role": "academy_admin",
        "academy_id": academy_id,
        "email_verified": email_verified,
        "email_verified_at": datetime.utcnow().timestamp() if email_verified else None,
        **plan_fields,
    }
    await db.users.insert_one(user_doc)
    await db.academies.update_one({"academy_id": academy_id}, {"$push": {"admins": user.username}})
    await log_workspace_event(
        current,
        action="academy_member.created",
        entity_type="user",
        entity_id=user.username,
        summary=f"Added academy admin {user.username}.",
        target_user=user.username,
        academy_id=academy_id,
    )
    try:
        await send_onboarding_emails(user_doc)
    except Exception:
        pass
    return {"username": user.username, "academy_id": academy_id}

@router.post("/{academy_id}/staff")
async def add_staff(
    academy_id: str,
    user: UserIn,
    can_add_students: bool = False,
    current: UserInDB = Depends(dependencies.get_current_active_user),
):
    academy = await db.academies.find_one({"academy_id": academy_id})
    if not academy:
        raise HTTPException(status_code=404, detail="Academy not found")
    org = await db.orgs.find_one({"org_id": academy_id})
    plan_fields = {}
    if org:
        plan_fields = {
            "org_id": org.get("org_id"),
            "plan_code": org.get("plan_code"),
            "plan_type": "organization",
            "plan_tier": org.get("plan_tier"),
        }

    existing = await auth.get_user(user.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")

    if has_any_role(current.role, ["academy_admin", "academyAdmin"]):
        if current.academy_id != academy_id:
            raise HTTPException(status_code=403, detail="Not academy admin of this academy")
    elif normalize_role(current.role) != "admin":
        raise HTTPException(status_code=403, detail="Insufficient privileges")

    try:
        hashed = get_password_hash(user.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    email_verified = False if user.email else True
    user_doc = {
        **user.dict(),
        "hashed_password": hashed,
        "role": "staff",
        "academy_id": academy_id,
        "can_add_students": can_add_students,
        "email_verified": email_verified,
        "email_verified_at": datetime.utcnow().timestamp() if email_verified else None,
        **plan_fields,
    }
    await db.users.insert_one(user_doc)
    await db.academies.update_one({"academy_id": academy_id}, {"$push": {"staff": user.username}})
    await log_workspace_event(
        current,
        action="academy_member.created",
        entity_type="user",
        entity_id=user.username,
        summary=f"Added staff member {user.username}.",
        target_user=user.username,
        academy_id=academy_id,
    )
    try:
        await send_onboarding_emails(user_doc)
    except Exception:
        pass
    return {"username": user.username, "academy_id": academy_id, "can_add_students": can_add_students}

@router.post("/{academy_id}/students")
async def add_student(
    academy_id: str,
    user: UserIn,
    current: UserInDB = Depends(dependencies.get_current_active_user),
):
    academy = await db.academies.find_one({"academy_id": academy_id})
    if not academy:
        raise HTTPException(status_code=404, detail="Academy not found")
    org = await db.orgs.find_one({"org_id": academy_id})
    plan_fields = {}
    if org:
        plan_fields = {
            "org_id": org.get("org_id"),
            "plan_code": org.get("plan_code"),
            "plan_type": "organization",
            "plan_tier": org.get("plan_tier"),
        }

    existing = await auth.get_user(user.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")

    # staff may only add student if permitted; academy_admin or admin always allowed
    current_role = normalize_role(current.role)

    if current_role == "staff":
        if not getattr(current, "can_add_students", False):
            raise HTTPException(status_code=403, detail="Staff not permitted to add students")
        if current.academy_id != academy_id:
            raise HTTPException(status_code=403, detail="Staff not in this academy")
    elif current_role == "academy_admin":
        if current.academy_id != academy_id:
            raise HTTPException(status_code=403, detail="Not academy admin of this academy")
    elif current_role != "admin":
        raise HTTPException(status_code=403, detail="Insufficient privileges")
    try:
        hashed = get_password_hash(user.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    email_verified = False if user.email else True
    user_doc = {
        **user.dict(),
        "hashed_password": hashed,
        "role": "student",
        "academy_id": academy_id,
        "sport_rules": build_default_rules_map(user.dict().get("angle_measurements")),
        "email_verified": email_verified,
        "email_verified_at": datetime.utcnow().timestamp() if email_verified else None,
        **plan_fields,
    }
    await db.users.insert_one(user_doc)
    await db.academies.update_one({"academy_id": academy_id}, {"$push": {"students": user.username}})
    await log_workspace_event(
        current,
        action="academy_member.created",
        entity_type="user",
        entity_id=user.username,
        summary=f"Added student {user.username}.",
        target_user=user.username,
        academy_id=academy_id,
    )
    try:
        await send_onboarding_emails(user_doc)
    except Exception:
        pass
    return {"username": user.username, "academy_id": academy_id}
