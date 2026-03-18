from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from .auth import get_user
from .roles import normalize_role
from ..schemas import UserInDB
from typing import Callable

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    from jose import JWTError, jwt
    from .auth import SECRET_KEY, ALGORITHM

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = await get_user(username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: UserInDB = Depends(get_current_user)):
    # could add extra checks (disabled flag etc.)
    return current_user


def require_role(role: str) -> Callable:
    async def role_checker(user: UserInDB = Depends(get_current_user)):
        if normalize_role(user.role) != normalize_role(role) and normalize_role(user.role) != "admin":
            raise HTTPException(status_code=403, detail="Insufficient privileges")
        return user
    return role_checker


async def get_current_active_admin(user: UserInDB = Depends(get_current_user)):
    if normalize_role(user.role) != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user
