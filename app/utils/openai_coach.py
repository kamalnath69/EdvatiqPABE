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
            "voice_enabled": True,
            "live_guidance_enabled": True,
            "voice_style": "calm",
        }
    return {
        "username": username,
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
    voice_enabled: bool | None = None,
    live_guidance_enabled: bool | None = None,
    voice_style: str | None = None,
) -> dict:
    current = await get_coach_settings(username)
    updates = {
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
