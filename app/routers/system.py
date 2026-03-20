import os

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from ..db import db
from ..schemas import AiPlatformSettingsIn, AiPlatformSettingsOut, SystemStatusOut
from ..utils import dependencies
from ..utils.openai_coach import get_platform_ai_settings, save_platform_ai_settings

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusOut)
async def get_system_status(current_user=Depends(dependencies.get_current_active_admin)):
    platform = await get_platform_ai_settings()
    collection_counts = {}
    for name in [
        "users",
        "sessions",
        "reports",
        "training_plans",
        "coach_reviews",
        "calendar_events",
        "notifications",
        "audit_logs",
        "invites",
    ]:
        collection_counts[name] = await db[name].count_documents({})

    enabled_features = [
        name
        for name, enabled in {
            "email": os.getenv("EMAIL_ENABLED", "true").lower() in ("1", "true", "yes"),
            "ai_chat": bool(platform.get("platform_key_available")),
            "billing": bool(os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET")),
            "workspace_search": True,
        }.items()
        if enabled
    ]

    return SystemStatusOut(
        database_ok=True,
        email_configured=bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD")),
        razorpay_configured=bool(os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET")),
        ai_configured=bool(platform.get("platform_key_available")),
        enabled_features=enabled_features,
        collection_counts=collection_counts,
    )


@router.get("/ai-settings", response_model=AiPlatformSettingsOut)
async def get_ai_settings(current_user=Depends(dependencies.get_current_active_admin)):
    platform = await get_platform_ai_settings()
    try:
        return AiPlatformSettingsOut(
            default_api_key_masked=platform.get("default_api_key_masked"),
            platform_key_available=bool(platform.get("platform_key_available")),
            credit_rate_per_1k_tokens=float(platform.get("credit_rate_per_1k_tokens", 1)),
            inr_per_credit=float(platform.get("inr_per_credit", 1)),
            suggested_top_up=float(platform.get("suggested_top_up", 100)),
            api_key_source=platform.get("api_key_source"),
        )
    except ValidationError as exc:
        raise ValueError("Invalid AI platform settings stored in database.") from exc


@router.put("/ai-settings", response_model=AiPlatformSettingsOut)
async def update_ai_settings(
    payload: AiPlatformSettingsIn,
    current_user=Depends(dependencies.get_current_active_admin),
):
    saved = await save_platform_ai_settings(
        default_api_key=payload.default_api_key,
        credit_rate_per_1k_tokens=payload.credit_rate_per_1k_tokens,
        inr_per_credit=payload.inr_per_credit,
        suggested_top_up=payload.suggested_top_up,
    )
    return AiPlatformSettingsOut(
        default_api_key_masked=saved.get("default_api_key_masked"),
        platform_key_available=bool(saved.get("platform_key_available")),
        credit_rate_per_1k_tokens=float(saved.get("credit_rate_per_1k_tokens", 1)),
        inr_per_credit=float(saved.get("inr_per_credit", 1)),
        suggested_top_up=float(saved.get("suggested_top_up", 100)),
        api_key_source=saved.get("api_key_source"),
    )
