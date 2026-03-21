from fastapi import APIRouter, Body, Depends, HTTPException
from typing import Optional
from datetime import datetime

from ..db import db
from ..schemas import CoachChatRequest, CoachConfigIn, CoachConfigOut, CoachLiveRequest, UserInDB
from ..utils import dependencies
from ..utils.openai_coach import (
    OPENAI_COACH_MODEL,
    build_chat_messages,
    charge_wallet_for_usage,
    create_client,
    extract_text_response,
    extract_total_tokens,
    get_coach_settings,
    get_openai_api_key,
    get_platform_ai_settings,
    get_wallet_summary,
    mask_api_key,
    parse_json_response,
    resolve_runtime_api_key,
    save_coach_settings,
)

router = APIRouter(prefix="/chat", tags=["chat"])
LIVE_GUIDANCE_CACHE: dict[str, dict] = {}


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


def _clean_context_blob(value: dict | None) -> str:
    if not value:
        return ""
    parts = []
    for key, raw in value.items():
        if raw in (None, "", [], {}):
            continue
        parts.append(f"{key}: {raw}")
    return "\n".join(parts)


async def _build_profile_context(current_user: UserInDB) -> str:
    profile_parts = [
        f"Role: {current_user.role}",
        f"Assigned sport: {getattr(current_user, 'assigned_sport', None) or 'unknown'}",
        f"Experience level: {getattr(current_user, 'experience_level', None) or 'unknown'}",
        f"Dominant hand: {getattr(current_user, 'dominant_hand', None) or 'unknown'}",
    ]
    recent = await _get_recent_session_insights(current_user.username)
    if recent:
        profile_parts.append(f"Recent sessions: {recent}")
    return "\n".join(profile_parts)


def _coerce_live_payload(raw_payload: dict | None, current_user: UserInDB) -> CoachLiveRequest | None:
    raw = dict(raw_payload or {})
    sport = raw.get("sport") or raw.get("assigned_sport") or getattr(current_user, "assigned_sport", None)
    if not sport:
        return None

    feedback = raw.get("feedback")
    if isinstance(feedback, str):
        feedback = [feedback]
    if not isinstance(feedback, list):
        feedback = []

    angles = raw.get("angles")
    if not isinstance(angles, dict):
        angles = {}

    payload = {
        "sport": str(sport),
        "student": raw.get("student") or getattr(current_user, "username", None),
        "feedback": [str(item) for item in feedback if item not in (None, "")],
        "angles": angles,
        "session_score": raw.get("session_score", raw.get("sessionScore")),
        "phase": raw.get("phase"),
        "rep_count": raw.get("rep_count", raw.get("repCount")),
        "tracking_quality": raw.get("tracking_quality", raw.get("trackingQuality")),
        "drill_focus": raw.get("drill_focus", raw.get("drillFocus")),
        "custom_note": raw.get("custom_note", raw.get("customNote")),
        "temperature_c": raw.get("temperature_c", raw.get("temperatureC")),
        "pressure_kpa": raw.get("pressure_kpa", raw.get("pressureKpa")),
    }
    try:
        return CoachLiveRequest.model_validate(payload)
    except Exception:
        return None


@router.get("/config", response_model=CoachConfigOut)
async def get_config(current_user=Depends(dependencies.get_current_active_user)):
    settings = await get_coach_settings(current_user.username)
    api_key = await get_openai_api_key(current_user.username)
    wallet = await get_wallet_summary(current_user.username)
    platform = await get_platform_ai_settings()
    key_source = settings.get("key_source", "personal")
    platform_key_ready = bool(platform.get("platform_key_available"))
    configured = bool(api_key) if key_source == "personal" else platform_key_ready
    if not configured and key_source == "personal" and wallet.get("balance", 0) > 0 and platform_key_ready:
        configured = True
    return CoachConfigOut(
        configured=configured,
        api_key_masked=mask_api_key(api_key),
        key_source=key_source,
        platform_key_available=platform_key_ready,
        wallet_balance=wallet.get("balance", 0),
        wallet_currency=wallet.get("currency", "credits"),
        credit_rate_per_1k_tokens=float(platform.get("credit_rate_per_1k_tokens", 1)),
        inr_per_credit=float(platform.get("inr_per_credit", 1)),
        suggested_top_up=float(platform.get("suggested_top_up", 100)),
        voice_enabled=bool(settings.get("voice_enabled", True)),
        live_guidance_enabled=bool(settings.get("live_guidance_enabled", True)),
        voice_style=settings.get("voice_style", "calm"),
    )


@router.put("/config", response_model=CoachConfigOut)
async def update_config(payload: CoachConfigIn, current_user=Depends(dependencies.get_current_active_user)):
    saved = await save_coach_settings(
        current_user.username,
        api_key=payload.api_key,
        key_source=payload.key_source,
        voice_enabled=payload.voice_enabled,
        live_guidance_enabled=payload.live_guidance_enabled,
        voice_style=payload.voice_style,
    )
    api_key = await get_openai_api_key(current_user.username)
    wallet = await get_wallet_summary(current_user.username)
    platform = await get_platform_ai_settings()
    key_source = saved.get("key_source", "personal")
    platform_key_ready = bool(platform.get("platform_key_available"))
    configured = bool(api_key) if key_source == "personal" else platform_key_ready
    if not configured and key_source == "personal" and wallet.get("balance", 0) > 0 and platform_key_ready:
        configured = True
    return CoachConfigOut(
        configured=configured,
        api_key_masked=mask_api_key(api_key),
        key_source=key_source,
        platform_key_available=platform_key_ready,
        wallet_balance=wallet.get("balance", 0),
        wallet_currency=wallet.get("currency", "credits"),
        credit_rate_per_1k_tokens=float(platform.get("credit_rate_per_1k_tokens", 1)),
        inr_per_credit=float(platform.get("inr_per_credit", 1)),
        suggested_top_up=float(platform.get("suggested_top_up", 100)),
        voice_enabled=bool(saved.get("voice_enabled", True)),
        live_guidance_enabled=bool(saved.get("live_guidance_enabled", True)),
        voice_style=saved.get("voice_style", "calm"),
    )


@router.post("/ask")
async def ask(payload: CoachChatRequest, current_user=Depends(dependencies.get_current_active_user)):
    if not await _ai_chat_enabled(current_user):
        raise HTTPException(status_code=403, detail="AI coach is available on Pro plans only.")
    try:
        runtime = await resolve_runtime_api_key(current_user.username)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    history = [{"role": item.role, "text": item.text} for item in payload.messages if item.text.strip()]
    if not history:
        raise HTTPException(status_code=400, detail="At least one chat message is required.")

    docs = BASE_DOCS.copy()
    latest_user_message = history[-1]["text"]
    insights = await _get_recent_session_insights(current_user.username)
    if insights:
        docs.append({"id": "recent_sessions", "text": insights})
    ranked = sorted(docs, key=lambda d: _score(latest_user_message, d["text"]), reverse=True)
    top = ranked[:4]
    retrieved = [d["text"] for d in top if _score(latest_user_message, d["text"]) > 0]

    profile_context = await _build_profile_context(current_user)
    extra_context = _clean_context_blob(payload.context)
    system_prompt = (
        "You are Edvatiq's live performance coach. "
        "Be specific, practical, and conversational. Keep answers grounded in the athlete's current posture signals, "
        "recent sessions, and sport context. Use short paragraphs and actionable bullet points only when useful. "
        "If the athlete is asking for immediate training help, prioritize the next 1-3 corrections and a short drill. "
        "Never mention that you are reading a prompt.\n\n"
        f"Profile context:\n{profile_context}\n\n"
        f"Sport context: {payload.sport or getattr(current_user, 'assigned_sport', None) or 'unknown'}\n"
        f"Student context: {payload.student or current_user.username}\n"
        f"Retrieved coaching notes: {' '.join(retrieved) if retrieved else 'No matching notes.'}\n"
        f"Current UI context:\n{extra_context or 'None provided.'}"
    )
    client = create_client(runtime["api_key"])
    response = client.chat.completions.create(
        model=OPENAI_COACH_MODEL,
        temperature=0.7,
        messages=build_chat_messages(system_prompt, history),
    )
    answer = extract_text_response(response)
    total_tokens = extract_total_tokens(response)
    usage_charge = None
    if runtime["key_source"] == "platform":
        usage_charge = await charge_wallet_for_usage(
            current_user.username,
            tokens_used=total_tokens,
            source="ai_chat",
            model=OPENAI_COACH_MODEL,
            note="AI coach chat usage.",
        )
    return {
        "answer": answer,
        "context": " ".join(retrieved) if retrieved else "",
        "key_source": runtime["key_source"],
        "tokens_used": total_tokens,
        "credits_charged": abs(usage_charge["credits"]) if usage_charge else 0,
        "wallet_balance": usage_charge["balance_after"] if usage_charge else runtime["wallet"].get("balance", 0),
        "timestamp": datetime.utcnow().timestamp(),
    }


@router.post("/live-guidance")
async def live_guidance(
    raw_payload: dict = Body(default_factory=dict),
    current_user=Depends(dependencies.get_current_active_user),
):
    if not await _ai_chat_enabled(current_user):
        raise HTTPException(status_code=403, detail="AI coach is available on Pro plans only.")
    payload = _coerce_live_payload(raw_payload, current_user)
    if payload is None:
        return {
            "summary": "Waiting for a stable live session payload before generating a cue.",
            "cue": "Hold position and continue tracking.",
            "speak_now": False,
            "urgency": "low",
            "timestamp": datetime.utcnow().timestamp(),
        }
    settings = await get_coach_settings(current_user.username)
    if not settings.get("live_guidance_enabled", True):
        raise HTTPException(status_code=400, detail="Live AI guidance is disabled in your coach settings.")
    try:
        runtime = await resolve_runtime_api_key(current_user.username)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    fingerprint = str((raw_payload or {}).get("fingerprint") or "").strip()
    if fingerprint:
        cache_key = f"{current_user.username}:{fingerprint}"
        cached = LIVE_GUIDANCE_CACHE.get(cache_key)
        now_ts = datetime.utcnow().timestamp()
        if cached and now_ts - cached.get("timestamp", 0) < 45:
            return cached["response"]

    profile_context = await _build_profile_context(current_user)
    feedback = payload.feedback or []
    feedback_blob = "; ".join(feedback[:6]) if feedback else "No active correction messages."
    style = settings.get("voice_style", "calm")
    system_prompt = (
        "You are an elite live sports posture coach generating one immediate cue during active training. "
        "Return strict JSON with keys: summary, cue, speak_now, urgency. "
        "The cue must be a single short sentence a voice coach can say aloud while the athlete is moving. "
        "summary should be 1-2 short sentences for the dashboard. "
        "speak_now should be true when there is a clear actionable correction right now. "
        "urgency must be one of low, medium, high. "
        f"Voice style: {style}. "
        f"Profile context: {profile_context}"
    )
    user_prompt = (
        f"Sport: {payload.sport}\n"
        f"Student: {payload.student or current_user.username}\n"
        f"Session score: {payload.session_score if payload.session_score is not None else 'unknown'}\n"
        f"Phase: {payload.phase or 'unknown'}\n"
        f"Rep count: {payload.rep_count if payload.rep_count is not None else 'unknown'}\n"
        f"Tracking quality: {payload.tracking_quality or 'unknown'}\n"
        f"Temperature (C): {payload.temperature_c if payload.temperature_c is not None else 'unknown'}\n"
        f"Pressure (kPa): {payload.pressure_kpa if payload.pressure_kpa is not None else 'unknown'}\n"
        f"Drill focus: {payload.drill_focus or 'none'}\n"
        f"Coach note: {payload.custom_note or 'none'}\n"
        f"Active feedback: {feedback_blob}\n"
        f"Angles: {payload.angles or {}}"
    )
    client = create_client(runtime["api_key"])
    response = client.chat.completions.create(
        model=OPENAI_COACH_MODEL,
        temperature=0.4,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = extract_text_response(response)
    parsed = parse_json_response(raw, "Stay tall, slow down, and clean up one cue at a time.")
    total_tokens = extract_total_tokens(response)
    usage_charge = None
    if runtime["key_source"] == "platform":
        usage_charge = await charge_wallet_for_usage(
            current_user.username,
            tokens_used=total_tokens,
            source="live_guidance",
            model=OPENAI_COACH_MODEL,
            note="Live guidance usage.",
        )
    parsed["timestamp"] = datetime.utcnow().timestamp()
    parsed["key_source"] = runtime["key_source"]
    parsed["tokens_used"] = total_tokens
    parsed["credits_charged"] = abs(usage_charge["credits"]) if usage_charge else 0
    parsed["wallet_balance"] = usage_charge["balance_after"] if usage_charge else runtime["wallet"].get("balance", 0)
    if fingerprint:
        LIVE_GUIDANCE_CACHE[f"{current_user.username}:{fingerprint}"] = {
            "timestamp": parsed["timestamp"],
            "response": parsed,
        }
    return parsed
