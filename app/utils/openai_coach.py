import base64
import hashlib
import json
import os
from datetime import datetime
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from openai import OpenAI

from ..db import db
from .auth import SECRET_KEY

OPENAI_COACH_MODEL = os.getenv("OPENAI_COACH_MODEL", "gpt-4.1-mini")
VOICE_STYLE_OPTIONS = {"calm", "directive", "energetic"}
KEY_SOURCE_OPTIONS = {"personal", "platform"}
DEFAULT_CREDIT_RATE_PER_1K_TOKENS = float(os.getenv("OPENAI_CREDITS_PER_1K_TOKENS", "1"))
DEFAULT_SUGGESTED_TOPUP = float(os.getenv("WALLET_SUGGESTED_TOPUP_CREDITS", "100"))
DEFAULT_INR_PER_CREDIT = float(os.getenv("WALLET_INR_PER_CREDIT", "1"))


def _build_fernet() -> Fernet:
    digest = hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_api_key(value: str) -> str:
    fernet = _build_fernet()
    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_api_key(value: str) -> str:
    fernet = _build_fernet()
    try:
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Stored OpenAI API key could not be decrypted with the current SECRET_KEY.") from exc


def mask_api_key(value: str | None) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip()
    if len(cleaned) <= 8:
        return "*" * len(cleaned)
    return f"{cleaned[:6]}{'*' * max(4, len(cleaned) - 10)}{cleaned[-4:]}"


async def get_coach_settings(username: str) -> dict:
    doc = await db.ai_settings.find_one({"username": username})
    if not doc:
        return {
            "username": username,
            "key_source": "personal",
            "voice_enabled": True,
            "live_guidance_enabled": True,
            "voice_style": "calm",
        }
    return {
        "username": username,
        "key_source": doc.get("key_source") if doc.get("key_source") in KEY_SOURCE_OPTIONS else "personal",
        "voice_enabled": bool(doc.get("voice_enabled", True)),
        "live_guidance_enabled": bool(doc.get("live_guidance_enabled", True)),
        "voice_style": doc.get("voice_style") if doc.get("voice_style") in VOICE_STYLE_OPTIONS else "calm",
        "api_key_encrypted": doc.get("api_key_encrypted"),
        "updated_at": doc.get("updated_at"),
    }


async def save_coach_settings(
    username: str,
    *,
    api_key: str | None = None,
    key_source: str | None = None,
    voice_enabled: bool | None = None,
    live_guidance_enabled: bool | None = None,
    voice_style: str | None = None,
) -> dict:
    current = await get_coach_settings(username)
    updates = {
        "key_source": (
            current.get("key_source", "personal")
            if key_source is None
            else (key_source if key_source in KEY_SOURCE_OPTIONS else "personal")
        ),
        "voice_enabled": current.get("voice_enabled", True) if voice_enabled is None else bool(voice_enabled),
        "live_guidance_enabled": (
            current.get("live_guidance_enabled", True)
            if live_guidance_enabled is None
            else bool(live_guidance_enabled)
        ),
        "voice_style": (
            current.get("voice_style", "calm")
            if voice_style is None
            else (voice_style if voice_style in VOICE_STYLE_OPTIONS else "calm")
        ),
        "updated_at": datetime.utcnow().timestamp(),
    }
    encrypted = current.get("api_key_encrypted")
    if api_key is not None:
        clean = api_key.strip()
        encrypted = _encrypt_api_key(clean) if clean else None
    updates["api_key_encrypted"] = encrypted
    await db.ai_settings.update_one({"username": username}, {"$set": {"username": username, **updates}}, upsert=True)
    saved = await get_coach_settings(username)
    saved["api_key_encrypted"] = encrypted
    return saved


async def get_openai_api_key(username: str) -> Optional[str]:
    settings = await get_coach_settings(username)
    encrypted = settings.get("api_key_encrypted")
    if not encrypted:
        return None
    return _decrypt_api_key(encrypted)


def get_platform_openai_api_key() -> Optional[str]:
    return (os.getenv("OPENAI_API_KEY") or "").strip() or None


async def get_platform_ai_settings() -> dict:
    doc = await db.ai_platform_settings.find_one({"id": "default"})
    stored_key_encrypted = doc.get("default_api_key_encrypted") if doc else None
    stored_key = _decrypt_api_key(stored_key_encrypted) if stored_key_encrypted else None
    env_key = get_platform_openai_api_key()
    runtime_key = stored_key or env_key
    return {
        "default_api_key_masked": mask_api_key(runtime_key),
        "platform_key_available": bool(runtime_key),
        "api_key_source": "admin" if stored_key else ("env" if env_key else None),
        "default_api_key_encrypted": stored_key_encrypted,
        "default_api_key": runtime_key,
        "credit_rate_per_1k_tokens": float((doc or {}).get("credit_rate_per_1k_tokens", DEFAULT_CREDIT_RATE_PER_1K_TOKENS)),
        "inr_per_credit": float((doc or {}).get("inr_per_credit", DEFAULT_INR_PER_CREDIT)),
        "suggested_top_up": float((doc or {}).get("suggested_top_up", DEFAULT_SUGGESTED_TOPUP)),
        "updated_at": (doc or {}).get("updated_at"),
    }


async def save_platform_ai_settings(
    *,
    default_api_key: str | None = None,
    credit_rate_per_1k_tokens: float | None = None,
    inr_per_credit: float | None = None,
    suggested_top_up: float | None = None,
) -> dict:
    current = await get_platform_ai_settings()
    encrypted = current.get("default_api_key_encrypted")
    if default_api_key is not None:
        clean = default_api_key.strip()
        encrypted = _encrypt_api_key(clean) if clean else None
    doc = {
        "id": "default",
        "default_api_key_encrypted": encrypted,
        "credit_rate_per_1k_tokens": float(
            current.get("credit_rate_per_1k_tokens", DEFAULT_CREDIT_RATE_PER_1K_TOKENS)
            if credit_rate_per_1k_tokens is None
            else credit_rate_per_1k_tokens
        ),
        "inr_per_credit": float(
            current.get("inr_per_credit", DEFAULT_INR_PER_CREDIT) if inr_per_credit is None else inr_per_credit
        ),
        "suggested_top_up": float(
            current.get("suggested_top_up", DEFAULT_SUGGESTED_TOPUP) if suggested_top_up is None else suggested_top_up
        ),
        "updated_at": datetime.utcnow().timestamp(),
    }
    await db.ai_platform_settings.update_one({"id": "default"}, {"$set": doc}, upsert=True)
    return await get_platform_ai_settings()


def _round_credits(value: float) -> float:
    return round(max(value, 0), 2)


def calculate_credit_cost(tokens_used: int | None, credit_rate_per_1k_tokens: float) -> float:
    total_tokens = max(int(tokens_used or 0), 0)
    if total_tokens <= 0:
        return 0
    return _round_credits((total_tokens / 1000) * float(credit_rate_per_1k_tokens or 0))


async def get_wallet_summary(username: str) -> dict:
    platform = await get_platform_ai_settings()
    wallet = await db.wallets.find_one({"username": username})
    if not wallet:
        settings = await get_coach_settings(username)
        personal_key = await get_openai_api_key(username)
        return {
            "username": username,
            "balance": 0.0,
            "currency": "credits",
            "preferred_key_source": settings.get("key_source", "personal"),
            "personal_key_configured": bool(personal_key),
            "platform_key_available": bool(platform.get("platform_key_available")),
            "default_credit_rate_per_1k_tokens": float(platform.get("credit_rate_per_1k_tokens", DEFAULT_CREDIT_RATE_PER_1K_TOKENS)),
            "inr_per_credit": float(platform.get("inr_per_credit", DEFAULT_INR_PER_CREDIT)),
            "suggested_top_up": float(platform.get("suggested_top_up", DEFAULT_SUGGESTED_TOPUP)),
            "updated_at": None,
        }
    settings = await get_coach_settings(username)
    personal_key = await get_openai_api_key(username)
    return {
        "username": username,
        "balance": _round_credits(wallet.get("balance", 0)),
        "currency": wallet.get("currency", "credits"),
        "preferred_key_source": settings.get("key_source", "personal"),
        "personal_key_configured": bool(personal_key),
        "platform_key_available": bool(platform.get("platform_key_available")),
        "default_credit_rate_per_1k_tokens": float(platform.get("credit_rate_per_1k_tokens", DEFAULT_CREDIT_RATE_PER_1K_TOKENS)),
        "inr_per_credit": float(platform.get("inr_per_credit", DEFAULT_INR_PER_CREDIT)),
        "suggested_top_up": wallet.get("suggested_top_up", float(platform.get("suggested_top_up", DEFAULT_SUGGESTED_TOPUP))),
        "updated_at": wallet.get("updated_at"),
    }


async def list_wallet_transactions(username: str, limit: int = 25) -> list[dict]:
    cursor = db.wallet_transactions.find({"username": username}).sort("created_at", -1).limit(max(1, min(limit, 100)))
    items = []
    async for doc in cursor:
        clean = dict(doc)
        clean.pop("_id", None)
        items.append(clean)
    return items


async def top_up_wallet(
    username: str,
    *,
    credits: float,
    amount_inr: float | None = None,
    source: str = "manual_topup",
    note: str | None = None,
) -> dict:
    credits_value = _round_credits(credits)
    if credits_value <= 0:
        raise ValueError("credits must be greater than zero")
    current = await get_wallet_summary(username)
    platform = await get_platform_ai_settings()
    balance_after = _round_credits(current.get("balance", 0) + credits_value)
    updated_at = datetime.utcnow().timestamp()
    wallet_doc = {
        "username": username,
        "balance": balance_after,
        "currency": "credits",
        "suggested_top_up": current.get("suggested_top_up", float(platform.get("suggested_top_up", DEFAULT_SUGGESTED_TOPUP))),
        "updated_at": updated_at,
    }
    await db.wallets.update_one({"username": username}, {"$set": wallet_doc}, upsert=True)
    transaction = {
        "id": f"wallet_txn_{os.urandom(6).hex()}",
        "username": username,
        "type": "top_up",
        "credits": credits_value,
        "balance_after": balance_after,
        "amount_inr": amount_inr if amount_inr is not None else _round_credits(credits_value * float(platform.get("inr_per_credit", DEFAULT_INR_PER_CREDIT))),
        "tokens_used": None,
        "source": source,
        "model": None,
        "note": note or "Wallet credits added.",
        "created_at": updated_at,
    }
    await db.wallet_transactions.insert_one(transaction)
    return transaction


async def charge_wallet_for_usage(
    username: str,
    *,
    tokens_used: int | None,
    source: str,
    model: str,
    note: str | None = None,
) -> dict:
    platform = await get_platform_ai_settings()
    cost = calculate_credit_cost(tokens_used, float(platform.get("credit_rate_per_1k_tokens", DEFAULT_CREDIT_RATE_PER_1K_TOKENS)))
    summary = await get_wallet_summary(username)
    current_balance = _round_credits(summary.get("balance", 0))
    if cost > current_balance:
        raise RuntimeError("Insufficient wallet credits for platform AI usage.")
    balance_after = _round_credits(current_balance - cost)
    updated_at = datetime.utcnow().timestamp()
    await db.wallets.update_one(
        {"username": username},
        {"$set": {"username": username, "balance": balance_after, "currency": "credits", "updated_at": updated_at}},
        upsert=True,
    )
    transaction = {
        "id": f"wallet_txn_{os.urandom(6).hex()}",
        "username": username,
        "type": "usage",
        "credits": -cost,
        "balance_after": balance_after,
        "amount_inr": None,
        "tokens_used": int(tokens_used or 0),
        "source": source,
        "model": model,
        "note": note or "AI platform usage charge.",
        "created_at": updated_at,
    }
    await db.wallet_transactions.insert_one(transaction)
    return transaction


async def resolve_runtime_api_key(username: str) -> dict:
    settings = await get_coach_settings(username)
    preferred = settings.get("key_source", "personal")
    personal_key = await get_openai_api_key(username)
    platform = await get_platform_ai_settings()
    platform_key = platform.get("default_api_key")
    wallet = await get_wallet_summary(username)
    if preferred == "personal":
        if personal_key:
            return {
                "api_key": personal_key,
                "key_source": "personal",
                "settings": settings,
                "wallet": wallet,
            }
        if platform_key and wallet.get("balance", 0) > 0:
            return {
                "api_key": platform_key,
                "key_source": "platform",
                "settings": settings,
                "wallet": wallet,
            }
        raise RuntimeError("OpenAI API key not configured. Add your own key or switch to the default key with wallet credits.")
    if not platform_key:
        raise RuntimeError("Default platform AI key is not available right now.")
    if wallet.get("balance", 0) <= 0:
        raise RuntimeError("Add wallet credits to use the default AI key.")
    return {
        "api_key": platform_key,
        "key_source": "platform",
        "settings": settings,
        "wallet": wallet,
    }


def extract_total_tokens(response) -> int:
    usage = getattr(response, "usage", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if total_tokens is None and isinstance(usage, dict):
        total_tokens = usage.get("total_tokens")
    if total_tokens is None:
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage is not None else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage is not None else 0
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
            completion_tokens = usage.get("completion_tokens", completion_tokens)
        total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
    return max(int(total_tokens or 0), 0)


def build_chat_messages(system_prompt: str, messages: list[dict]) -> list[dict]:
    result = [{"role": "system", "content": system_prompt}]
    for item in messages[-12:]:
        role = "assistant" if item.get("role") == "assistant" else "user"
        text = str(item.get("text") or "").strip()
        if text:
            result.append({"role": role, "content": text})
    return result


def create_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def extract_text_response(response) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    choices = getattr(response, "choices", None) or []
    if choices:
        content = getattr(choices[0].message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
    raise RuntimeError("OpenAI response did not contain text output.")


def parse_json_response(raw: str, fallback_summary: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "summary": fallback_summary,
            "cue": raw.strip() or fallback_summary,
            "speak_now": True,
            "urgency": "medium",
        }
    return {
        "summary": str(data.get("summary") or fallback_summary).strip(),
        "cue": str(data.get("cue") or fallback_summary).strip(),
        "speak_now": bool(data.get("speak_now", True)),
        "urgency": str(data.get("urgency") or "medium").strip().lower(),
    }
