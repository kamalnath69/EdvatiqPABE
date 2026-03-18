from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime

from ..db import db
from ..utils import dependencies

router = APIRouter(prefix="/chat", tags=["chat"])


BASE_DOCS = [
    {
        "id": "posture_basics",
        "text": "Keep shoulders level, spine tall, hips square, and maintain consistent stance width for stable posture.",
    },
    {
        "id": "archery_release",
        "text": "For archery, stabilize bow shoulder, keep elbow alignment smooth, and follow through without dropping the bow arm.",
    },
    {
        "id": "training_consistency",
        "text": "Shorter, consistent sessions improve motor learning. Track session scores and focus on one correction at a time.",
    },
    {
        "id": "camera_quality",
        "text": "Good lighting and full body framing improve pose detection. Avoid backlight and keep limbs visible.",
    },
]


def _tokenize(text: str) -> set[str]:
    return {w for w in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(w) > 2}


def _score(query: str, doc: str) -> int:
    q = _tokenize(query)
    d = _tokenize(doc)
    return len(q & d)


async def _get_recent_session_insights(username: str) -> Optional[str]:
    cursor = db.sessions.find({"student": username}).sort("timestamp", -1).limit(3)
    notes = []
    async for s in cursor:
        score = s.get("session_score")
        sport = s.get("sport")
        feedback = s.get("feedback") or []
        msg = f"Recent session for {sport}: score {score}, corrections: {', '.join(feedback[:3])}"
        notes.append(msg)
    if not notes:
        return None
    return " ".join(notes)


async def _resolve_plan_code(current_user) -> Optional[str]:
    if not current_user:
        return None
    if getattr(current_user, "plan_code", None):
        return current_user.plan_code
    org_id = getattr(current_user, "org_id", None) or getattr(current_user, "academy_id", None)
    if not org_id:
        return None
    org = await db.orgs.find_one({"org_id": org_id})
    if org:
        return org.get("plan_code")
    return None


async def _ai_chat_enabled(current_user) -> bool:
    if not current_user:
        return False
    if getattr(current_user, "role", "") == "admin":
        return True
    plan_code = await _resolve_plan_code(current_user)
    if plan_code:
        feature_doc = await db.plan_features.find_one({"code": plan_code})
        if feature_doc and "ai_chat" in feature_doc:
            return bool(feature_doc.get("ai_chat"))
    if getattr(current_user, "plan_tier", None) == "pro":
        return True
    org_id = getattr(current_user, "org_id", None) or getattr(current_user, "academy_id", None)
    if org_id:
        org = await db.orgs.find_one({"org_id": org_id})
        if org and org.get("plan_tier") == "pro":
            return True
    return False


@router.post("/ask")
async def ask(question: str, current_user=Depends(dependencies.get_current_active_user)):
    if not await _ai_chat_enabled(current_user):
        raise HTTPException(status_code=403, detail="AI coach is available on Pro plans only.")
    # Basic lightweight RAG: retrieve from docs + recent session summaries.
    docs = BASE_DOCS.copy()
    if current_user:
        insights = await _get_recent_session_insights(current_user.username)
        if insights:
            docs.append({"id": "recent_sessions", "text": insights})

    ranked = sorted(docs, key=lambda d: _score(question, d["text"]), reverse=True)
    top = ranked[:3]
    context = " ".join([d["text"] for d in top if _score(question, d["text"]) > 0]) or "No matching context."

    response = (
        f"Based on your data and coaching knowledge: {context} "
        f"Try to focus on one correction at a time, and re-test after 3-5 focused reps."
    )
    return {
        "answer": response,
        "context": context,
        "timestamp": datetime.utcnow().timestamp(),
    }
