from fastapi import APIRouter, Depends

from ..db import db
from ..schemas import SearchResultOut
from ..utils import dependencies
from ..utils.roles import has_any_role, normalize_role
from ..utils.workspace import clean_doc

router = APIRouter(prefix="/search", tags=["search"])


def _matches(doc: dict, q: str, fields: list[str]) -> bool:
    haystack = " ".join(str(doc.get(field, "")) for field in fields).lower()
    return q.lower() in haystack


def _result(kind: str, identifier: str, title: str, subtitle: str, href: str, icon: str, scope: str) -> SearchResultOut:
    return SearchResultOut(type=kind, id=identifier, title=title, subtitle=subtitle, href=href, icon=icon, roleScope=scope)


@router.get("/", response_model=list[SearchResultOut])
async def global_search(q: str, current_user=Depends(dependencies.get_current_active_user)):
    term = (q or "").strip().lower()
    if len(term) < 2:
        return []
    role = normalize_role(current_user.role)
    results: list[SearchResultOut] = []

    user_query = {}
    session_query = {}
    common_query = {}
    if role == "student":
        user_query = {"username": current_user.username}
        session_query = {"student": current_user.username}
        common_query = {"$or": [{"owner": current_user.username}, {"student": current_user.username}]}
    elif has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]):
        user_query = {"academy_id": current_user.academy_id}
        session_query = {"academy_id": current_user.academy_id}
        common_query = {"academy_id": current_user.academy_id}

    async for user in db.users.find(user_query):
        doc = clean_doc(user)
        if _matches(doc, term, ["username", "full_name", "email"]):
            results.append(_result("user", doc["username"], doc.get("full_name") or doc["username"], doc.get("role", ""), "/dashboard", "user", role))
    async for session in db.sessions.find(session_query):
        doc = clean_doc(session)
        if _matches(doc, term, ["student", "sport", "custom_note", "drill_focus"]):
            results.append(_result("session", doc.get("id", doc.get("student", "session")), f"{doc.get('student')} · {doc.get('sport')}", doc.get("custom_note") or "Session record", "/dashboard", "activity", role))
    for collection_name, kind, fields in [
        ("reports", "report", ["title", "summary", "student", "sport"]),
        ("training_plans", "training_plan", ["title", "summary", "student", "coach_comments"]),
        ("coach_reviews", "coach_review", ["title", "summary", "student", "notes"]),
        ("calendar_events", "calendar", ["title", "description", "student", "location"]),
        ("notifications", "notification", ["summary", "action", "entity_type"]),
    ]:
        async for doc in db[collection_name].find(common_query):
            item = clean_doc(doc)
            if _matches(item, term, fields):
                results.append(_result(kind, item["id"], item.get("title") or item.get("summary") or item["id"], item.get("student") or item.get("entity_type") or "", "/dashboard", kind, role))
    return results[:20]
