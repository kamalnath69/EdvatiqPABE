import os
import re
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
import razorpay

from ..db import db
from ..schemas import CheckoutInitIn, CheckoutVerifyIn, PlanInfo, PlanFeaturesIn, UserOut
from ..utils.auth import get_password_hash
from ..utils.notifications import send_onboarding_emails
from ..utils.verification import is_signup_email_verified
from ..utils import dependencies

router = APIRouter(prefix="/billing", tags=["billing"])

EMAIL_VERIFICATION_REQUIRED = os.getenv("EMAIL_VERIFICATION_REQUIRED", "true").lower() in ("1", "true", "yes")


PLANS = [
    PlanInfo(code="personal_basic", name="Personal Basic", amount_inr=499, plan_type="personal", tier="basic"),
    PlanInfo(code="personal_pro", name="Personal Pro", amount_inr=999, plan_type="personal", tier="pro"),
    PlanInfo(code="org_basic", name="Organization Basic", amount_inr=4999, plan_type="organization", tier="basic"),
    PlanInfo(code="org_pro", name="Organization Pro", amount_inr=9999, plan_type="organization", tier="pro"),
]

DEFAULT_PLAN_FEATURES = {
    "personal_basic": {
        "description": "For solo athletes getting started.",
        "features": ["Live posture tracking", "Session history + score", "Core training analytics"],
        "ai_chat": False,
        "ai_analytics": False,
    },
    "personal_pro": {
        "description": "Advanced tools for serious training.",
        "features": ["Everything in Personal Basic", "AI coach chat", "AI session intelligence"],
        "ai_chat": True,
        "ai_analytics": True,
    },
    "org_basic": {
        "description": "Starter plan for academies and teams.",
        "features": ["Academy admin workspace", "Staff + student management", "Shared dashboards"],
        "ai_chat": False,
        "ai_analytics": False,
    },
    "org_pro": {
        "description": "Enterprise-grade scale and reporting.",
        "features": ["Everything in Org Basic", "AI coach chat", "AI analytics suite"],
        "ai_chat": True,
        "ai_analytics": True,
    },
}


def _get_plan(plan_code: str) -> PlanInfo | None:
    for plan in PLANS:
        if plan.code == plan_code:
            return plan
    return None


async def _get_plan_features(plan_code: str) -> dict:
    doc = await db.plan_features.find_one({"code": plan_code})
    if doc:
        return doc
    defaults = DEFAULT_PLAN_FEATURES.get(plan_code, {"description": "", "features": [], "ai_chat": False, "ai_analytics": False})
    doc = {
        "code": plan_code,
        "description": defaults.get("description", ""),
        "features": defaults.get("features", []),
        "ai_chat": defaults.get("ai_chat", False),
        "ai_analytics": defaults.get("ai_analytics", False),
        "updated_at": datetime.utcnow().timestamp(),
    }
    await db.plan_features.insert_one(doc)
    return doc


def _slugify(text: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return raw or "org"


def _get_razorpay_client() -> razorpay.Client:
    key_id = os.getenv("RAZORPAY_KEY_ID", "")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        raise HTTPException(status_code=500, detail="Razorpay keys are not configured.")
    return razorpay.Client(auth=(key_id, key_secret))


@router.get("/plans", response_model=list[PlanInfo])
async def list_plans():
    results = []
    for plan in PLANS:
        features = await _get_plan_features(plan.code)
        data = plan.dict()
        data.update(
            {
                "description": features.get("description"),
                "features": features.get("features", []),
                "ai_chat": features.get("ai_chat", False),
                "ai_analytics": features.get("ai_analytics", False),
            }
        )
        results.append(PlanInfo(**data))
    return results


@router.put("/plans/{plan_code}", response_model=PlanInfo)
async def update_plan_features(
    plan_code: str,
    payload: PlanFeaturesIn,
    current_user=Depends(dependencies.get_current_active_admin),
):
    plan = _get_plan(plan_code)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    doc = {
        "code": plan.code,
        "description": payload.description or "",
        "features": payload.features or [],
        "ai_chat": bool(payload.ai_chat),
        "ai_analytics": bool(payload.ai_analytics),
        "updated_at": datetime.utcnow().timestamp(),
    }
    await db.plan_features.update_one({"code": plan.code}, {"$set": doc}, upsert=True)
    data = plan.dict()
    data.update(
        {
            "description": doc["description"],
            "features": doc["features"],
            "ai_chat": doc["ai_chat"],
            "ai_analytics": doc["ai_analytics"],
        }
    )
    return PlanInfo(**data)


@router.post("/create-order")
async def create_order(payload: CheckoutInitIn):
    plan = _get_plan(payload.plan_code)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid plan selection.")
    if plan.plan_type == "organization" and not payload.org_name:
        raise HTTPException(status_code=400, detail="Organization name is required for organization plans.")
    if not payload.email:
        raise HTTPException(status_code=400, detail="Email is required for plan activation.")
    if EMAIL_VERIFICATION_REQUIRED and not await is_signup_email_verified(payload.email):
        raise HTTPException(status_code=403, detail="Email verification required before checkout.")

    existing_user = await db.users.find_one({"username": payload.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered.")

    client = _get_razorpay_client()
    order = client.order.create(
        {
            "amount": plan.amount_inr * 100,
            "currency": plan.currency,
            "receipt": f"rcpt_{payload.username}_{uuid.uuid4().hex[:8]}",
            "notes": {
                "plan_code": plan.code,
                "username": payload.username,
                "plan_type": plan.plan_type,
            },
        }
    )
    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "plan": plan,
        "key_id": os.getenv("RAZORPAY_KEY_ID"),
    }


@router.post("/verify", response_model=UserOut)
async def verify_payment(payload: CheckoutVerifyIn):
    plan = _get_plan(payload.plan_code)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid plan selection.")
    if plan.plan_type == "organization" and not payload.org_name:
        raise HTTPException(status_code=400, detail="Organization name is required for organization plans.")
    if not payload.email:
        raise HTTPException(status_code=400, detail="Email is required for plan activation.")
    if EMAIL_VERIFICATION_REQUIRED and not await is_signup_email_verified(payload.email):
        raise HTTPException(status_code=403, detail="Email verification required before checkout.")

    existing_user = await db.users.find_one({"username": payload.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered.")

    client = _get_razorpay_client()
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payload.razorpay_order_id,
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Payment verification failed: {exc}") from exc

    org_id = None
    academy_id = None
    role = "student"
    if plan.plan_type == "organization":
        slug = _slugify(payload.org_name)
        org_id = f"{slug}-{uuid.uuid4().hex[:6]}"
        academy_id = org_id
        role = "academy_admin"
        await db.academies.insert_one(
            {
                "academy_id": academy_id,
                "name": payload.org_name,
                "address": "",
                "city": "",
                "state": "",
                "country": "",
                "contact_email": payload.email,
                "contact_phone": None,
                "admins": [payload.username],
                "staff": [],
                "students": [],
            }
        )
        await db.orgs.insert_one(
            {
                "org_id": org_id,
                "name": payload.org_name,
                "owner": payload.username,
                "plan_code": plan.code,
                "plan_tier": plan.tier,
                "created_at": datetime.utcnow().timestamp(),
            }
        )

    email_verified = False if payload.email else True
    user_doc = {
        "username": payload.username,
        "hashed_password": get_password_hash(payload.password),
        "role": role,
        "academy_id": academy_id,
        "org_id": org_id,
        "full_name": payload.full_name,
        "email": payload.email,
        "email_verified": email_verified,
        "email_verified_at": datetime.utcnow().timestamp() if email_verified else None,
        "plan_code": plan.code,
        "plan_type": plan.plan_type,
        "plan_tier": plan.tier,
    }
    await db.users.insert_one(user_doc)

    await db.payments.insert_one(
        {
            "username": payload.username,
            "plan_code": plan.code,
            "plan_type": plan.plan_type,
            "plan_tier": plan.tier,
            "razorpay_order_id": payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "created_at": datetime.utcnow().timestamp(),
        }
    )

    try:
        await send_onboarding_emails(user_doc)
    except Exception:
        pass

    return UserOut(**user_doc)
