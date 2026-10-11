
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from jwt import InvalidTokenError
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel


load_dotenv()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# JWT Configuration
# ---------------------------------------------------------

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY must be configured in .env "
        "with at least 32 characters."
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# ---------------------------------------------------------
# OAuth2 Authentication Scheme
# ---------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login"
)


# ---------------------------------------------------------
# User and Token Models
# ---------------------------------------------------------

class AuthenticatedUser(BaseModel):
    username: str
    role: Literal["analyst", "administrator"]


# ---------------------------------------------------------
# Generate JWT Access Token
# ---------------------------------------------------------

def create_access_token(
    username: str,
    role: Literal["analyst", "administrator"]
) -> str:

    now = datetime.now(timezone.utc)

    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )


# ---------------------------------------------------------
# Validate JWT and Extract User
# ---------------------------------------------------------

def get_current_user(
    token: str = Depends(oauth2_scheme)
) -> AuthenticatedUser:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"}
    )

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "require": ["sub", "role", "iat", "exp"]
            }
        )

        username = payload.get("sub")
        role = payload.get("role")

        if (
            not isinstance(username, str)
            or not username.strip()
            or role not in ("analyst", "administrator")
        ):
            raise credentials_exception

        return AuthenticatedUser(
            username=username,
            role=role
        )

    except InvalidTokenError:
        raise credentials_exception


# ---------------------------------------------------------
# Role-Based Authorization Dependency
# ---------------------------------------------------------

def require_roles(*allowed_roles: str):

    def role_checker(
        current_user: AuthenticatedUser = Depends(
            get_current_user
        )
    ) -> AuthenticatedUser:

        if current_user.role not in allowed_roles:

            logger.warning(
                "Access denied for user %s",
                current_user.username
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )

        return current_user

    return role_checker


# ---------------------------------------------------------
# Reusable Role Dependencies
# ---------------------------------------------------------

require_analyst_or_admin = require_roles(
    "analyst",
    "administrator"
)

require_admin = require_roles(
    "administrator"
)
