from datetime import datetime

from fastapi import APIRouter, Depends

from ..db import db
from ..schemas import FavoriteIn, FavoriteOut
from ..utils import dependencies
from ..utils.workspace import list_collection, make_id

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("/", response_model=list[FavoriteOut])
async def list_favorites(current_user=Depends(dependencies.get_current_active_user)):
    return await list_collection("favorites", {"owner": current_user.username}, sort=[("created_at", -1)])


@router.post("/", response_model=FavoriteOut)
async def create_favorite(payload: FavoriteIn, current_user=Depends(dependencies.get_current_active_user)):
    doc = {
        "id": make_id("fav"),
        **payload.dict(),
        "owner": current_user.username,
        "created_at": datetime.utcnow().timestamp(),
    }
    await db.favorites.update_one(
        {"owner": current_user.username, "entity_type": payload.entity_type, "entity_id": payload.entity_id},
        {"$set": doc},
        upsert=True,
    )
    saved = await db.favorites.find_one({"owner": current_user.username, "entity_type": payload.entity_type, "entity_id": payload.entity_id})
    saved.pop("_id", None)
    return saved


@router.delete("/{favorite_id}")
async def delete_favorite(favorite_id: str, current_user=Depends(dependencies.get_current_active_user)):
    await db.favorites.delete_one({"id": favorite_id, "owner": current_user.username})
    return {"detail": "Favorite removed."}
