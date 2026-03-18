from fastapi import APIRouter, Depends, HTTPException
from typing import List
from datetime import datetime

from ..db import db
from ..schemas import PolicyIn, PolicyOut
from ..utils import dependencies

router = APIRouter(prefix="/policies", tags=["policies"])

ALLOWED_KEYS = {"privacy", "terms"}

DEFAULT_POLICIES = {
    "privacy": {
        "title": "Privacy Policy",
        "body": (
            "Edvatiq collects only the data needed to provide performance tracking, including account details, "
            "session metrics, and usage analytics.\n\n"
            "We do not sell personal information. Data is stored securely and only shared with authorized staff "
            "within your organization.\n\n"
            "You can request data export or deletion by contacting support."
        ),
    },
    "terms": {
        "title": "Terms and Conditions",
        "body": (
            "Edvatiq provides performance analysis tools for athletes and organizations. By using the platform, "
            "you agree to follow applicable sports safety guidelines and local regulations.\n\n"
            "Subscriptions renew monthly unless canceled. Please contact support for billing and plan changes.\n\n"
            "Content and session data remain available to authorized users within your organization."
        ),
    },
}


def _normalize_doc(doc: dict) -> dict:
    if not doc:
        return {}
    doc = {**doc}
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


async def _get_or_seed_policy(key: str) -> dict:
    doc = await db.policies.find_one({"key": key})
    if doc:
        return doc
    default = DEFAULT_POLICIES.get(key, {"title": key.replace("_", " ").title(), "body": ""})
    doc = {
        "key": key,
        "title": default["title"],
        "body": default["body"],
        "updated_at": datetime.utcnow().timestamp(),
    }
    result = await db.policies.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return doc


@router.get("", response_model=List[PolicyOut])
async def list_policies(current_user=Depends(dependencies.get_current_active_admin)):
    results = []
    cursor = db.policies.find().sort("updated_at", -1)
    async for doc in cursor:
        results.append(PolicyOut(**_normalize_doc(doc)))
    return results


@router.get("/{key}", response_model=PolicyOut)
async def get_policy(key: str):
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=404, detail="Policy not found")
    doc = await _get_or_seed_policy(key)
    return PolicyOut(**_normalize_doc(doc))


@router.put("/{key}", response_model=PolicyOut)
async def upsert_policy(
    key: str,
    payload: PolicyIn,
    current_user=Depends(dependencies.get_current_active_admin),
):
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=404, detail="Policy not found")
    doc = {
        "key": key,
        "title": payload.title,
        "body": payload.body,
        "updated_at": datetime.utcnow().timestamp(),
    }
    await db.policies.update_one({"key": key}, {"$set": doc}, upsert=True)
    saved = await db.policies.find_one({"key": key})
    return PolicyOut(**_normalize_doc(saved))
