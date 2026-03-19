import os
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from ..db import db
from .roles import has_any_role, normalize_role


INVITE_TTL_HOURS = int(os.getenv("INVITE_TTL_HOURS", "168"))


def now_ts() -> float:
    return datetime.utcnow().timestamp()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def clean_doc(doc: dict | None) -> dict | None:
    if not doc:
        return None
    data = dict(doc)
    data.pop("_id", None)
    return data


def clean_docs(docs: list[dict]) -> list[dict]:
    return [clean_doc(doc) for doc in docs if doc]


async def list_collection(collection_name: str, query: dict | None = None, sort: list[tuple[str, int]] | None = None) -> list[dict]:
    cursor = db[collection_name].find(query or {})
    if sort:
        cursor = cursor.sort(sort)
    return clean_docs([doc async for doc in cursor])


async def get_user_or_404(username: str) -> dict:
    user = await db.users.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return clean_doc(user)


async def require_student_access(target_username: str, current_user) -> dict:
    student = await get_user_or_404(target_username)
    if normalize_role(student.get("role")) != "student":
        raise HTTPException(status_code=404, detail="Student not found")

    current_role = normalize_role(current_user.role)
    if current_role == "student" and current_user.username != target_username:
        raise HTTPException(status_code=403, detail="Students can only access their own records")
    if has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]) and student.get("academy_id") != current_user.academy_id:
        raise HTTPException(status_code=403, detail="Cannot access student outside academy")
    return student


def ensure_staff_scope(current_user):
    if not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")


def can_manage_academy_scope(current_user, academy_id: str | None) -> bool:
    if normalize_role(current_user.role) == "admin":
        return True
    return has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]) and current_user.academy_id == academy_id


async def create_notification(
    target_user: str,
    action: str,
    entity_type: str,
    summary: str,
    actor: str | None = None,
    entity_id: str | None = None,
    academy_id: str | None = None,
    org_id: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    doc = {
        "id": make_id("notif"),
        "actor": actor,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "summary": summary,
        "target_user": target_user,
        "academy_id": academy_id,
        "org_id": org_id,
        "metadata": metadata or {},
        "read": False,
        "created_at": now_ts(),
    }
    await db.notifications.insert_one(doc)
    return doc


async def create_audit_log(
    actor: str | None,
    action: str,
    entity_type: str,
    summary: str,
    entity_id: str | None = None,
    academy_id: str | None = None,
    org_id: str | None = None,
    target_user: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    doc = {
        "id": make_id("audit"),
        "actor": actor,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "summary": summary,
        "academy_id": academy_id,
        "org_id": org_id,
        "target_user": target_user,
        "metadata": metadata or {},
        "created_at": now_ts(),
    }
    await db.audit_logs.insert_one(doc)
    return doc


async def log_workspace_event(
    actor_user,
    action: str,
    entity_type: str,
    summary: str,
    entity_id: str | None = None,
    target_user: str | None = None,
    academy_id: str | None = None,
    org_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    notify_users: list[str] | None = None,
):
    resolved_academy = academy_id if academy_id is not None else getattr(actor_user, "academy_id", None)
    resolved_org = org_id if org_id is not None else getattr(actor_user, "org_id", None)
    actor = getattr(actor_user, "username", None) if actor_user else None
    await create_audit_log(
        actor=actor,
        action=action,
        entity_type=entity_type,
        summary=summary,
        entity_id=entity_id,
        academy_id=resolved_academy,
        org_id=resolved_org,
        target_user=target_user,
        metadata=metadata,
    )
    for username in notify_users or []:
        await create_notification(
            target_user=username,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary,
            academy_id=resolved_academy,
            org_id=resolved_org,
            metadata=metadata,
        )


async def list_academy_usernames(academy_id: str | None) -> list[str]:
    if not academy_id:
        return []
    cursor = db.users.find({"academy_id": academy_id}, {"username": 1})
    return [doc.get("username") async for doc in cursor]


def build_default_user_settings(existing: dict | None = None) -> dict:
    data = existing or {}
    return {
        "theme": data.get("theme", "light"),
        "density": data.get("density", "comfortable"),
        "layout": data.get("layout", "workspace"),
        "quick_search_enabled": data.get("quick_search_enabled", True),
        "notifications_email": data.get("notifications_email", True),
        "notifications_in_app": data.get("notifications_in_app", True),
        "onboarding_seen": data.get("onboarding_seen", False),
        "camera_defaults": data.get("camera_defaults", {"quality": "balanced", "mirrored": True}),
        "live_defaults": data.get("live_defaults", {"voice_style": "calm", "auto_save": True}),
    }


def build_default_academy_settings(existing: dict | None = None, academy_id: str | None = None) -> dict:
    data = existing or {}
    return {
        "academy_id": academy_id or data.get("academy_id"),
        "branding": data.get("branding", {"workspace_name": "Edvatiq", "accent": "#2563eb"}),
        "support": data.get("support", {"email": os.getenv("SUPPORT_EMAIL", "support@edvatiq.com")}),
        "notification_defaults": data.get("notification_defaults", {"email_digest": "daily", "review_alerts": True}),
        "sport_policies": data.get("sport_policies", {}),
        "reminder_defaults": data.get("reminder_defaults", {"session_reminder_minutes": 30}),
    }
