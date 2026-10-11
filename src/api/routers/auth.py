
import os
import secrets
from typing import Literal

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from pwdlib import PasswordHash

from src.api.security import (
    AuthenticatedUser,
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)


load_dotenv()

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)

password_hash = PasswordHash.recommended()


# ---------------------------------------------------------
# Response Models
# ---------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: Literal["analyst", "administrator"]


# ---------------------------------------------------------
# Load Configured Users
# ---------------------------------------------------------

def get_configured_users():

    return {
        "analyst": {
            "role": "analyst",
            "password_hash": os.getenv(
                "ANALYST_PASSWORD_HASH"
            )
        },
        "administrator": {
            "role": "administrator",
            "password_hash": os.getenv(
                "ADMIN_PASSWORD_HASH"
            )
        }
    }


# ---------------------------------------------------------
# Authenticate User
# ---------------------------------------------------------

def authenticate_user(
    username: str,
    password: str
):

    users = get_configured_users()

    user = users.get(username)

    if user is None:
        return None

    stored_hash = user["password_hash"]

    if not stored_hash:
        return None

    try:
        password_valid = password_hash.verify(
            password,
            stored_hash
        )
    except (ValueError, TypeError):
        return None

    if not password_valid:
        return None

    return AuthenticatedUser(
        username=username,
        role=user["role"]
    )


# ---------------------------------------------------------
# Login API
# ---------------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends()
):

    user = authenticate_user(
        form_data.username,
        form_data.password
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={
                "WWW-Authenticate": "Bearer"
            }
        )

    access_token = create_access_token(
        username=user.username,
        role=user.role
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role
    )


# ---------------------------------------------------------
# Current User API
# ---------------------------------------------------------

@router.get(
    "/me",
    response_model=AuthenticatedUser
)
def get_my_profile(
    current_user: AuthenticatedUser = Depends(
        get_current_user
    )
):
    return current_user
