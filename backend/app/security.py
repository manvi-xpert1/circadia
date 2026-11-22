"""Local login: Argon2 password hashes and HTTP-only session cookies.

There is exactly one account. Session tokens are random; only their SHA-256
hash is stored, so a copy of the database cannot be used to log in.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import LOCKOUT_SECONDS, MAX_FAILED_LOGINS, SESSION_COOKIE, SESSION_DAYS
from .db import get_db
from .models import LoginSession, User

_hasher = PasswordHasher()
_failures = {"count": 0, "locked_until": 0.0}


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_lockout() -> None:
    remaining = _failures["locked_until"] - time.monotonic()
    if remaining > 0:
        raise HTTPException(429, {"code": "LOCKED", "message": f"Too many wrong attempts. Try again in {int(remaining) + 1} s."})


def record_failure() -> None:
    _failures["count"] += 1
    if _failures["count"] >= MAX_FAILED_LOGINS:
        _failures["count"] = 0
        _failures["locked_until"] = time.monotonic() + LOCKOUT_SECONDS


def reset_failures() -> None:
    _failures["count"] = 0
    _failures["locked_until"] = 0.0


def start_session(db: Session, user: User, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    db.execute(delete(LoginSession).where(LoginSession.expires_at < datetime.now()))
    db.add(LoginSession(token_hash=_token_hash(token), user_id=user.id, expires_at=datetime.now() + timedelta(days=SESSION_DAYS)))
    db.commit()
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/"
    )


def end_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == _token_hash(token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


def user_from_request(db: Session, request: Request) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    sess = db.get(LoginSession, _token_hash(token))
    if sess is None or sess.expires_at < datetime.now():
        return None
    return db.get(User, sess.user_id)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_from_request(db, request)
    if user is None:
        raise HTTPException(401, {"code": "NOT_LOGGED_IN", "message": "Please log in."})
    return user


def the_user(db: Session) -> User | None:
    return db.scalar(select(User).limit(1))
