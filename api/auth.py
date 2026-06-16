"""Auth JWT simple — un solo usuario admin (credenciales en env vars)."""
import os
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.environ.get("JWT_SECRET", "cambia-esto-en-produccion")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_HASH = os.environ.get("ADMIN_HASH", "")  # bcrypt hash de la contraseña


def verify_password(plain: str) -> bool:
    if not ADMIN_HASH:
        return False
    return pwd_ctx.verify(plain, ADMIN_HASH)


def create_token() -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": ADMIN_USER, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = payload.get("sub")
        if not user:
            raise exc
        return user
    except JWTError:
        raise exc
