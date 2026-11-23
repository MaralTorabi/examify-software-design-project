"""Argon2 password handling and bearer authentication."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash

from core.errors import AuthenticationError
from core.schemas import TokenResponse, UserOut
from core.types import Role

passwords = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = passwords.hash("invalid-login-placeholder")
bearer = HTTPBearer(auto_error=False)
ISSUER = "examify-api"


def hash_password(password: str) -> str:
    return passwords.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    return passwords.verify(password, stored_hash)


def issue_token(user_id: UUID, secret: str, expires_minutes: int) -> TokenResponse:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iss": ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return TokenResponse(access_token=jwt.encode(payload, secret, algorithm="HS256"))


def verify_token(token: str, secret: str) -> UUID:
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=ISSUER,
            options={"require": ["sub", "iss", "iat", "exp"]},
        )
        return UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired access token.") from exc


def public_user(row) -> UserOut:
    return UserOut(
        id=row["id"], email=row["email"], created_at=row["created_at"], role=Role.STUDENT
    )


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> UserOut:
    if credentials is None:
        raise AuthenticationError("A bearer access token is required.")
    user_id = verify_token(credentials.credentials, request.app.state.jwt_secret)
    with request.app.state.store.transaction() as connection:
        row = connection.execute(
            "SELECT * FROM prototype_users WHERE id = ?", (str(user_id),)
        ).fetchone()
    if row is None:
        raise AuthenticationError("Invalid or expired access token.")
    return public_user(row)


CurrentUser = Annotated[UserOut, Depends(get_current_user)]
