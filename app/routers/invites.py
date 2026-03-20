import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..db import db
from ..schemas import InviteAcceptIn, InviteIn, InviteOut
from ..utils import dependencies
from ..utils.auth import get_password_hash
from ..utils.email import build_invite_email, send_email
from ..utils.notifications import send_onboarding_emails
from ..utils.roles import has_any_role, normalize_role
from ..utils.workspace import list_collection, log_workspace_event, make_id

router = APIRouter(prefix="/invites", tags=["invites"])


@router.get("/", response_model=list[InviteOut])
async def list_invites(current_user=Depends(dependencies.get_current_active_user)):
    if not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")
    query = {}
    if normalize_role(current_user.role) != "admin":
        query["academy_id"] = current_user.academy_id
    return await list_collection("invites", query, sort=[("created_at", -1)])


@router.post("/", response_model=InviteOut)
async def create_invite(payload: InviteIn, current_user=Depends(dependencies.get_current_active_user)):
    if not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")
    academy_id = payload.academy_id or current_user.academy_id
    if normalize_role(current_user.role) != "admin" and academy_id != current_user.academy_id:
        raise HTTPException(status_code=403, detail="Cannot invite outside academy")
    existing = await db.invites.find_one({"email": payload.email, "status": "pending"})
    if existing:
        raise HTTPException(status_code=400, detail="Pending invite already exists for this email")
    now = datetime.utcnow().timestamp()
    token = secrets.token_urlsafe(24)
    doc = {
        "id": make_id("invite"),
        **payload.dict(),
        "academy_id": academy_id,
        "org_id": payload.org_id or getattr(current_user, "org_id", None),
        "invited_by": current_user.username,
        "token": token,
        "status": "pending",
        "created_at": now,
        "expires_at": now + 7 * 24 * 3600,
        "accepted_at": None,
    }
    await db.invites.insert_one(doc)
    subject, html, text = build_invite_email(token, payload.full_name or payload.email.split("@")[0], payload.role)
    try:
        send_email(payload.email, subject, html, text)
    except Exception:
        pass
    await log_workspace_event(
        current_user,
        action="invite.created",
        entity_type="invite",
        entity_id=doc["id"],
        summary=f"Sent {payload.role} invite to {payload.email}.",
        academy_id=academy_id,
    )
    return doc


@router.post("/accept")
async def accept_invite(payload: InviteAcceptIn):
    invite = await db.invites.find_one({"token": payload.token})
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Invite is no longer active")
    if invite.get("expires_at", 0) < datetime.utcnow().timestamp():
        raise HTTPException(status_code=400, detail="Invite has expired")
    existing = await db.users.find_one({"username": payload.username})
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")
    email_verified = False if invite.get("email") else True
    user_doc = {
        "username": payload.username,
        "hashed_password": get_password_hash(payload.password),
        "role": normalize_role(invite.get("role")),
        "academy_id": invite.get("academy_id"),
        "org_id": invite.get("org_id"),
        "full_name": payload.full_name or invite.get("full_name"),
        "email": invite.get("email"),
        "email_verified": email_verified,
        "email_verified_at": datetime.utcnow().timestamp() if email_verified else None,
    }
    await db.users.insert_one(user_doc)
    await db.invites.update_one(
        {"id": invite["id"]},
        {"$set": {"status": "accepted", "accepted_at": datetime.utcnow().timestamp(), "username": payload.username}},
    )
    if invite.get("academy_id"):
        role = normalize_role(invite.get("role"))
        field = "students"
        if role == "staff":
            field = "staff"
        if role == "academy_admin":
            field = "admins"
        await db.academies.update_one({"academy_id": invite.get("academy_id")}, {"$push": {field: payload.username}})
    try:
        await send_onboarding_emails(user_doc)
    except Exception:
        pass
    return {"detail": "Invite accepted successfully.", "username": payload.username}
