from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..db import db
from ..schemas import HelpArticleIn, HelpArticleOut
from ..utils import dependencies
from ..utils.roles import normalize_role
from ..utils.workspace import clean_doc, list_collection, log_workspace_event, make_id

router = APIRouter(prefix="/help-docs", tags=["help_docs"])

DEFAULT_HELP_ARTICLES = [
    {
        "title": "Getting Started",
        "body": "Create or review a session, confirm your rules profile, then move into goals, reports, and coach review. Use Quick Search to jump between pages without losing context.",
        "category": "onboarding",
        "audience": "all",
        "order": 1,
        "published": True,
    },
    {
        "title": "Using Reports",
        "body": "Reports summarize session trends, export PDF snapshots, and generate share tokens for coaches or academy stakeholders.",
        "category": "reports",
        "audience": "all",
        "order": 2,
        "published": True,
    },
    {
        "title": "Training Plans",
        "body": "Training plans connect goals, weekly focus, coach comments, and completion tracking so athletes can see exactly what to work on next.",
        "category": "training",
        "audience": "all",
        "order": 3,
        "published": True,
    },
    {
        "title": "Coach Review Workflow",
        "body": "Compare sessions, annotate key frames, attach media metadata, approve progress, and save structured feedback for the athlete.",
        "category": "reviews",
        "audience": "all",
        "order": 4,
        "published": True,
    },
]


async def _ensure_seed_articles():
    count = await db.help_docs.count_documents({})
    if count:
        return
    now = datetime.utcnow().timestamp()
    for item in DEFAULT_HELP_ARTICLES:
        await db.help_docs.insert_one(
            {
                "id": make_id("help"),
                **item,
                "created_by": "system",
                "created_at": now,
                "updated_at": now,
            }
        )


@router.get("/", response_model=list[HelpArticleOut])
async def list_help_articles(current_user=Depends(dependencies.get_current_active_user)):
    await _ensure_seed_articles()
    query = {"published": True}
    if normalize_role(current_user.role) == "admin":
        query = {}
    return await list_collection("help_docs", query, sort=[("order", 1), ("updated_at", -1)])


@router.post("/", response_model=HelpArticleOut)
async def create_help_article(payload: HelpArticleIn, current_user=Depends(dependencies.get_current_active_admin)):
    now = datetime.utcnow().timestamp()
    doc = {
        "id": make_id("help"),
        **payload.dict(),
        "created_by": current_user.username,
        "created_at": now,
        "updated_at": now,
    }
    await db.help_docs.insert_one(doc)
    await log_workspace_event(
        current_user,
        action="help_article.created",
        entity_type="help_article",
        entity_id=doc["id"],
        summary=f"Created help article {payload.title}.",
    )
    return doc


@router.put("/{article_id}", response_model=HelpArticleOut)
async def update_help_article(article_id: str, payload: HelpArticleIn, current_user=Depends(dependencies.get_current_active_admin)):
    article = await db.help_docs.find_one({"id": article_id})
    if not article:
        raise HTTPException(status_code=404, detail="Help article not found")
    updates = {**payload.dict(), "updated_at": datetime.utcnow().timestamp()}
    await db.help_docs.update_one({"id": article_id}, {"$set": updates})
    updated = clean_doc(await db.help_docs.find_one({"id": article_id}))
    await log_workspace_event(
        current_user,
        action="help_article.updated",
        entity_type="help_article",
        entity_id=article_id,
        summary=f"Updated help article {updated.get('title', article_id)}.",
    )
    return updated


@router.delete("/{article_id}")
async def delete_help_article(article_id: str, current_user=Depends(dependencies.get_current_active_admin)):
    await db.help_docs.delete_one({"id": article_id})
    await log_workspace_event(
        current_user,
        action="help_article.deleted",
        entity_type="help_article",
        entity_id=article_id,
        summary="Deleted help article.",
    )
    return {"detail": "Help article deleted."}
