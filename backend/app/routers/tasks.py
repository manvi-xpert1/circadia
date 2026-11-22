"""Task CRUD with filters and sorting."""
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Task, User
from ..schemas import TaskIn, TaskOut, TaskPatch
from ..security import current_user
from ..services.planner import get_prefs
from ..services.recurrence import ensure_copies, refresh_future_copies

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

SORTS = {
    "deadline": lambda t: (t.deadline is None, t.deadline or datetime.max),
    "priority": lambda t: -t.priority,
    "created": lambda t: t.created_at,
    "title": lambda t: t.title.lower(),
    "duration": lambda t: t.est_minutes,
}


def _sync(db: Session, user: User) -> None:
    ensure_copies(db, user, date.today(), get_prefs(db, user).horizon_days)


def _get(db: Session, user: User, task_id: int) -> Task:
    t = db.get(Task, task_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Task not found."})
    return t


def _check_dependency(db: Session, user: User, task_id: Optional[int], dep_id: Optional[int]) -> None:
    if dep_id is None:
        return
    if dep_id == task_id:
        raise HTTPException(422, {"code": "BAD_DEPENDENCY", "message": "A task cannot depend on itself."})
    dep = db.get(Task, dep_id)
    if dep is None or dep.user_id != user.id:
        raise HTTPException(422, {"code": "BAD_DEPENDENCY", "message": "The prerequisite task does not exist."})
    if dep.recur_days:
        raise HTTPException(422, {"code": "BAD_DEPENDENCY", "message": "Choose one day's copy of a repeating task, not the repeating task itself."})
    # Walk the chain to refuse circles.
    seen = {task_id}
    while dep is not None and dep.depends_on_id is not None:
        if dep.depends_on_id in seen:
            raise HTTPException(422, {"code": "BAD_DEPENDENCY", "message": "That would create a circle of prerequisites."})
        seen.add(dep.id)
        dep = db.get(Task, dep.depends_on_id)


@router.get("", response_model=list[TaskOut])
def list_tasks(
    status: Optional[Literal["pending", "done", "missed", "all"]] = "all",
    category: Optional[str] = None,
    priority: Optional[int] = Query(default=None, ge=1, le=4),
    kind: Optional[Literal["fixed", "movable"]] = None,
    source: Optional[str] = None,
    sort: Literal["deadline", "priority", "created", "title", "duration"] = "deadline",
    upcoming: bool = False,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _sync(db, user)
    q = select(Task).where(Task.user_id == user.id)
    if not upcoming:  # copies of repeating tasks for later days stay hidden until their day
        q = q.where((Task.occurrence_date.is_(None)) | (Task.occurrence_date <= date.today()))
    if status and status != "all":
        q = q.where(Task.status == status)
    if category:
        q = q.where(Task.category == category)
    if priority:
        q = q.where(Task.priority == priority)
    if kind:
        q = q.where(Task.is_fixed.is_(kind == "fixed"))
    if source:
        q = q.where(Task.source == source)
    rows = list(db.scalars(q))
    rows.sort(key=SORTS[sort])
    return rows


@router.post("", response_model=TaskOut, status_code=201)
def create_task(body: TaskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _check_dependency(db, user, None, body.depends_on_id)
    t = Task(user_id=user.id, **body.model_dump())
    db.add(t)
    db.commit()
    if t.recur_days:
        _sync(db, user)
    return t


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _get(db, user, task_id)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, body: TaskPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _get(db, user, task_id)
    data = body.model_dump(exclude_unset=True)
    was_template = bool(t.recur_days)
    if t.parent_id is not None and data.get("recur_days"):
        raise HTTPException(422, {"code": "INVALID", "message": "This is one day's copy. Change the repeating task itself instead.", "field": "recur_days"})
    if was_template and "status" in data:
        raise HTTPException(409, {"code": "REPEATING", "message": "Mark one day's copy done, not the repeating task."})
    if "depends_on_id" in data:
        _check_dependency(db, user, t.id, data["depends_on_id"])
    for k, v in data.items():
        setattr(t, k, v)
    # Re-validate the whole task after a partial update.
    try:
        TaskIn.model_validate({c: getattr(t, c) for c in TaskIn.model_fields})
    except Exception as e:  # pydantic ValidationError
        db.rollback()
        raise HTTPException(422, {"code": "INVALID", "message": str(e).splitlines()[-1] if str(e) else "Invalid task"})
    if data.get("status") == "done" and t.completed_at is None:
        t.completed_at = datetime.now()
    if data.get("status") == "pending":
        t.completed_at = None
    db.commit()
    if was_template or t.recur_days:
        refresh_future_copies(db, t, date.today())
        _sync(db, user)
    return t


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _get(db, user, task_id)
    if t.recur_days:
        raise HTTPException(409, {"code": "REPEATING", "message": "Mark one day's copy done, not the repeating task."})
    t.status = "done"
    t.completed_at = datetime.now()
    db.commit()
    return t


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _get(db, user, task_id)
    if t.recur_days:  # stop repeating: remove upcoming untouched copies, keep finished history
        t.recur_until = date.today() - timedelta(days=1)
        refresh_future_copies(db, t, date.today())
    db.delete(t)
    db.commit()
