"""First-run account creation, login, logout and password change."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, UserPreferences
from ..schemas import LoginIn, PasswordChangeIn, SetupIn
from ..security import (
    check_lockout, current_user, end_session, hash_password, record_failure, reset_failures,
    start_session, the_user, user_from_request, verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def me(user: User) -> dict:
    return {"id": user.id, "username": user.username, "display_name": user.display_name}


@router.get("/status")
def status(request: Request, db: Session = Depends(get_db)):
    user = user_from_request(db, request)
    return {"has_account": the_user(db) is not None, "logged_in": user is not None, "user": me(user) if user else None}


@router.post("/setup", status_code=201)
def setup(body: SetupIn, response: Response, db: Session = Depends(get_db)):
    if the_user(db) is not None:
        raise HTTPException(409, {"code": "ACCOUNT_EXISTS", "message": "An account already exists on this computer."})
    user = User(username=body.username, password_hash=hash_password(body.password),
                display_name=(body.display_name or body.username).strip())
    db.add(user)
    db.flush()
    db.add(UserPreferences(user_id=user.id))
    db.commit()
    start_session(db, user, response)
    return me(user)


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    check_lockout()
    user = the_user(db)
    if user is None:
        raise HTTPException(409, {"code": "NO_ACCOUNT", "message": "Create your account first."})
    if body.username.strip().lower() != user.username.lower() or not verify_password(body.password, user.password_hash):
        record_failure()
        raise HTTPException(401, {"code": "BAD_LOGIN", "message": "Name or password is not right."})
    reset_failures()
    start_session(db, user, response)
    return me(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    end_session(db, request, response)
    return {"ok": True}


@router.post("/password")
def change_password(body: PasswordChangeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, {"code": "BAD_PASSWORD", "message": "Current password is not right."})
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
