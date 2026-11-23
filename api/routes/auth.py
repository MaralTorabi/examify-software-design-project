import re
import sqlite3
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from api.auth import DUMMY_PASSWORD_HASH, hash_password, issue_token, public_user, verify_password
from core.errors import AuthenticationError, ConflictError, ValidationError
from core.schemas import TokenResponse, UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class Credentials(BaseModel):
    email: Annotated[str, Field(max_length=254)]
    password: Annotated[str, Field(min_length=8, max_length=128)]


@router.post("/register", status_code=201)
def register(body: Credentials, request: Request) -> UserOut:
    email = body.email.strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValidationError("Enter a valid email address.")
    user = {
        "id": str(uuid4()),
        "email": email,
        "password_hash": hash_password(body.password),
        "created_at": datetime.now(UTC).isoformat(),
    }
    try:
        with request.app.state.store.transaction(write=True) as connection:
            connection.execute(
                "INSERT INTO prototype_users VALUES (:id, :email, :password_hash, :created_at)",
                user,
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("An account already exists for this email.") from exc
    return public_user(user)


@router.post("/login")
def login(body: Credentials, request: Request) -> TokenResponse:
    with request.app.state.store.transaction() as connection:
        user = connection.execute(
            "SELECT * FROM prototype_users WHERE email = ?", (body.email.strip().casefold(),)
        ).fetchone()
    stored_hash = user["password_hash"] if user else DUMMY_PASSWORD_HASH
    if not verify_password(body.password, stored_hash) or user is None:
        raise AuthenticationError("Invalid email or password.")
    return issue_token(
        public_user(user).id,
        request.app.state.jwt_secret,
        request.app.state.settings.jwt_expire_minutes,
    )
