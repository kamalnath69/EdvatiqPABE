import os
import hashlib
from datetime import datetime, timedelta
import bcrypt
from jose import JWTError, jwt
from typing import Optional, List

from ..db import db
from ..schemas import UserInDB

# load environment as needed
# (dotenv already loaded by db import)

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))

BCRYPT_MAX_PASSWORD_BYTES = 72
LONG_PASSWORD_PREFIX = "sha256$"


def _normalize_password(secret: str) -> str:
    raw = secret.encode("utf-8")
    if len(raw) <= BCRYPT_MAX_PASSWORD_BYTES:
        return secret
    # bcrypt truncates beyond 72 bytes; hash long secrets first to preserve full entropy.
    return f"{LONG_PASSWORD_PREFIX}{hashlib.sha256(raw).hexdigest()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    normalized = _normalize_password(plain_password).encode("utf-8")
    try:
        return bcrypt.checkpw(normalized, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    normalized = _normalize_password(password).encode("utf-8")
    return bcrypt.hashpw(normalized, bcrypt.gensalt()).decode("utf-8")


async def get_user(username: str) -> Optional[UserInDB]:
    user = await db.users.find_one({"username": username})
    if user:
        return UserInDB(**user)
    return None


async def authenticate_user(username: str, password: str):
    user = await get_user(username)
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user


async def list_users() -> List[dict]:
    users = []
    cursor = db.users.find()
    async for u in cursor:
        users.append(u)
    return users


async def create_user(user_data: dict):
    await db.users.insert_one(user_data)


async def delete_user(username: str):
    await db.users.delete_one({"username": username})


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
