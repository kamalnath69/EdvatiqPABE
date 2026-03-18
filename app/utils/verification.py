import hashlib
import os
import secrets
from datetime import datetime
from ..db import db
from .auth import SECRET_KEY

CODE_TTL_MINUTES = int(os.getenv("VERIFICATION_CODE_TTL_MINUTES", "15"))
SIGNUP_CODE_TTL_MINUTES = int(os.getenv("SIGNUP_VERIFICATION_TTL_MINUTES", "30"))


def _hash_code(code: str) -> str:
    raw = f"{code}{SECRET_KEY}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def generate_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


async def create_email_verification(username: str, email: str) -> str:
    code = generate_code()
    now = datetime.utcnow().timestamp()
    await db.email_verifications.update_many(
        {"username": username, "used": False},
        {"$set": {"used": True, "used_at": now}},
    )
    await db.email_verifications.insert_one(
        {
            "username": username,
            "email": email,
            "code_hash": _hash_code(code),
            "created_at": now,
            "expires_at": now + CODE_TTL_MINUTES * 60,
            "used": False,
        }
    )
    return code


async def consume_email_verification(username: str, email: str, code: str) -> bool:
    now = datetime.utcnow().timestamp()
    record = await db.email_verifications.find_one(
        {
            "code_hash": _hash_code(code),
            "used": False,
            "expires_at": {"$gt": now},
            "$or": [{"username": username}, {"email": email}],
        }
    )
    if not record:
        return False
    await db.email_verifications.update_one(
        {"_id": record["_id"]},
        {"$set": {"used": True, "used_at": now}},
    )
    return True


async def create_password_reset(username: str, email: str) -> str:
    code = generate_code()
    now = datetime.utcnow().timestamp()
    await db.password_resets.update_many(
        {"username": username, "used": False},
        {"$set": {"used": True, "used_at": now}},
    )
    await db.password_resets.insert_one(
        {
            "username": username,
            "email": email,
            "code_hash": _hash_code(code),
            "created_at": now,
            "expires_at": now + CODE_TTL_MINUTES * 60,
            "used": False,
        }
    )
    return code


async def consume_password_reset(username: str, email: str, code: str) -> bool:
    now = datetime.utcnow().timestamp()
    record = await db.password_resets.find_one(
        {
            "code_hash": _hash_code(code),
            "used": False,
            "expires_at": {"$gt": now},
            "$or": [{"username": username}, {"email": email}],
        }
    )
    if not record:
        return False
    await db.password_resets.update_one(
        {"_id": record["_id"]},
        {"$set": {"used": True, "used_at": now}},
    )
    return True


async def create_signup_verification(email: str) -> str:
    email = (email or "").strip().lower()
    code = generate_code()
    now = datetime.utcnow().timestamp()
    await db.signup_email_verifications.update_many(
        {"email": email, "used": False},
        {"$set": {"used": True, "used_at": now}},
    )
    await db.signup_email_verifications.insert_one(
        {
            "email": email,
            "code_hash": _hash_code(code),
            "created_at": now,
            "expires_at": now + SIGNUP_CODE_TTL_MINUTES * 60,
            "used": False,
        }
    )
    return code


async def consume_signup_verification(email: str, code: str) -> bool:
    email = (email or "").strip().lower()
    now = datetime.utcnow().timestamp()
    record = await db.signup_email_verifications.find_one(
        {
            "code_hash": _hash_code(code),
            "used": False,
            "expires_at": {"$gt": now},
            "email": email,
        }
    )
    if not record:
        return False
    await db.signup_email_verifications.update_one(
        {"_id": record["_id"]},
        {"$set": {"used": True, "used_at": now, "verified_at": now}},
    )
    return True


async def is_signup_email_verified(email: str) -> bool:
    email = (email or "").strip().lower()
    now = datetime.utcnow().timestamp()
    record = await db.signup_email_verifications.find_one(
        {
            "email": email,
            "used": True,
            "verified_at": {"$exists": True},
            "expires_at": {"$gt": now},
        }
    )
    return bool(record)
