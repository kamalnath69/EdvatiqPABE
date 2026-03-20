import os
from datetime import datetime

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import db
from ..schemas import (
    WalletRechargeInitIn,
    WalletRechargeOrderOut,
    WalletRechargeVerifyIn,
    WalletSummaryOut,
    WalletTopUpIn,
    WalletTransactionOut,
)
from ..utils import dependencies
from ..utils.openai_coach import get_platform_ai_settings, get_wallet_summary, list_wallet_transactions, top_up_wallet
from ..utils.workspace import log_workspace_event

router = APIRouter(prefix="/wallet", tags=["wallet"])


def _get_razorpay_client() -> razorpay.Client:
    key_id = os.getenv("RAZORPAY_KEY_ID", "")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        raise HTTPException(status_code=500, detail="Razorpay keys are not configured.")
    return razorpay.Client(auth=(key_id, key_secret))


@router.get("/summary", response_model=WalletSummaryOut)
async def wallet_summary(current_user=Depends(dependencies.get_current_active_user)):
    return await get_wallet_summary(current_user.username)


@router.get("/transactions", response_model=list[WalletTransactionOut])
async def wallet_transactions(
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(dependencies.get_current_active_user),
):
    return await list_wallet_transactions(current_user.username, limit=limit)


@router.post("/top-up", response_model=WalletSummaryOut)
async def wallet_top_up(payload: WalletTopUpIn, current_user=Depends(dependencies.get_current_active_user)):
    try:
        transaction = await top_up_wallet(
            current_user.username,
            credits=payload.credits,
            amount_inr=payload.amount_inr,
            source="workspace_topup",
            note=payload.note or "Wallet credits added from workspace settings.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await log_workspace_event(
        current_user,
        action="wallet.topup",
        entity_type="wallet",
        entity_id=current_user.username,
        summary=f"Added {payload.credits:.0f} wallet credits.",
        target_user=current_user.username,
        notify_users=[current_user.username],
        metadata={"transaction_id": transaction["id"], "credits": payload.credits},
    )
    return await get_wallet_summary(current_user.username)


@router.post("/create-order", response_model=WalletRechargeOrderOut)
async def wallet_create_order(
    payload: WalletRechargeInitIn,
    current_user=Depends(dependencies.get_current_active_user),
):
    platform = await get_platform_ai_settings()
    amount_inr = round(float(payload.credits) * float(platform.get("inr_per_credit", 1)), 2)
    if amount_inr <= 0:
        raise HTTPException(status_code=400, detail="Recharge amount must be greater than zero.")

    client = _get_razorpay_client()
    receipt = f"wallet_{current_user.username}_{int(datetime.utcnow().timestamp())}"
    order = client.order.create(
        {
            "amount": int(round(amount_inr * 100)),
            "currency": "INR",
            "receipt": receipt[:40],
            "notes": {
                "kind": "wallet_recharge",
                "username": current_user.username,
                "credits": f"{payload.credits:.2f}",
            },
        }
    )

    await db.wallet_orders.update_one(
        {"order_id": order["id"]},
        {
            "$set": {
                "order_id": order["id"],
                "username": current_user.username,
                "credits": payload.credits,
                "amount_inr": amount_inr,
                "currency": order["currency"],
                "note": payload.note or f"Recharge {payload.credits:.0f} wallet credits.",
                "status": "created",
                "created_at": datetime.utcnow().timestamp(),
            }
        },
        upsert=True,
    )

    return WalletRechargeOrderOut(
        order_id=order["id"],
        amount=order["amount"],
        currency=order["currency"],
        key_id=os.getenv("RAZORPAY_KEY_ID", ""),
        credits=payload.credits,
        amount_inr=amount_inr,
    )


@router.post("/verify-recharge", response_model=WalletSummaryOut)
async def wallet_verify_recharge(
    payload: WalletRechargeVerifyIn,
    current_user=Depends(dependencies.get_current_active_user),
):
    order_doc = await db.wallet_orders.find_one(
        {"order_id": payload.razorpay_order_id, "username": current_user.username}
    )
    if not order_doc:
        raise HTTPException(status_code=404, detail="Recharge order not found.")

    if order_doc.get("status") == "paid":
        return await get_wallet_summary(current_user.username)

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

    transaction = await top_up_wallet(
        current_user.username,
        credits=float(order_doc.get("credits", 0)),
        amount_inr=float(order_doc.get("amount_inr", 0)),
        source="razorpay_wallet_recharge",
        note=order_doc.get("note") or "Wallet recharge completed via Razorpay.",
    )

    paid_at = datetime.utcnow().timestamp()
    await db.wallet_orders.update_one(
        {"order_id": payload.razorpay_order_id},
        {
            "$set": {
                "status": "paid",
                "paid_at": paid_at,
                "razorpay_payment_id": payload.razorpay_payment_id,
            }
        },
    )
    await db.payments.insert_one(
        {
            "username": current_user.username,
            "kind": "wallet_recharge",
            "credits": float(order_doc.get("credits", 0)),
            "amount_inr": float(order_doc.get("amount_inr", 0)),
            "currency": order_doc.get("currency", "INR"),
            "razorpay_order_id": payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "created_at": paid_at,
        }
    )
    await log_workspace_event(
        current_user,
        action="wallet.topup",
        entity_type="wallet",
        entity_id=current_user.username,
        summary=f"Recharged {float(order_doc.get('credits', 0)):.0f} wallet credits via Razorpay.",
        target_user=current_user.username,
        notify_users=[current_user.username],
        metadata={
            "transaction_id": transaction["id"],
            "credits": float(order_doc.get("credits", 0)),
            "amount_inr": float(order_doc.get("amount_inr", 0)),
            "razorpay_order_id": payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
        },
    )
    return await get_wallet_summary(current_user.username)
