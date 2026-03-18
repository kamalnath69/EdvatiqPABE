from fastapi import APIRouter, Depends
from typing import List
from datetime import datetime

from ..db import db
from ..schemas import DemoLeadIn, SupportLeadIn, LeadOut
from ..utils import dependencies

router = APIRouter(prefix="/leads", tags=["leads"])


def _normalize_doc(doc: dict) -> dict:
    if not doc:
        return {}
    doc = {**doc}
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("/demo", response_model=LeadOut)
async def create_demo_lead(payload: DemoLeadIn):
    doc = payload.dict()
    doc["status"] = "new"
    doc["created_at"] = datetime.utcnow().timestamp()
    result = await db.lead_demo.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return LeadOut(**doc)


@router.get("/demo", response_model=List[LeadOut])
async def list_demo_leads(current_user=Depends(dependencies.get_current_active_admin)):
    results = []
    cursor = db.lead_demo.find().sort("created_at", -1)
    async for doc in cursor:
        results.append(LeadOut(**_normalize_doc(doc)))
    return results


@router.post("/support", response_model=LeadOut)
async def create_support_lead(payload: SupportLeadIn):
    doc = payload.dict()
    doc["status"] = "new"
    doc["created_at"] = datetime.utcnow().timestamp()
    result = await db.lead_support.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return LeadOut(**doc)


@router.get("/support", response_model=List[LeadOut])
async def list_support_leads(current_user=Depends(dependencies.get_current_active_admin)):
    results = []
    cursor = db.lead_support.find().sort("created_at", -1)
    async for doc in cursor:
        results.append(LeadOut(**_normalize_doc(doc)))
    return results
