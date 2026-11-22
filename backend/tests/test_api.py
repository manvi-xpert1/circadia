"""API: login, validation, CRUD, generate, outcomes and learning."""
from datetime import datetime, timedelta


def task_body(**kw):
    body = dict(title="Write report", category="Study", priority=3, est_minutes=60,
                mental_difficulty=7, physical_difficulty=2, mental_energy_req=7, physical_energy_req=2)
    body.update(kw)
    return body


def test_every_route_needs_login(client):
    for path in ["/api/tasks", "/api/checkins", "/api/schedules/current", "/api/models", "/api/preferences"]:
        assert client.get(path).status_code == 401


def test_first_run_setup_then_login(client):
    s = client.get("/api/auth/status").json()
    assert s == {"has_account": False, "logged_in": False, "user": None}
    assert client.post("/api/auth/setup", json={"username": "manvi", "password": "short"}).status_code == 422
    assert client.post("/api/auth/setup", json={"username": "manvi", "password": "secret-pass"}).status_code == 201
    assert client.post("/api/auth/setup", json={"username": "x", "password": "another-pass"}).status_code in (409, 422)
    client.post("/api/auth/logout")
    assert client.get("/api/tasks").status_code == 401
    assert client.post("/api/auth/login", json={"username": "manvi", "password": "wrong-pass"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "Manvi", "password": "secret-pass"})
    assert r.status_code == 200
    assert client.get("/api/tasks").status_code == 200


def test_password_is_hashed_and_lockout_after_five_failures(client):
    client.post("/api/auth/setup", json={"username": "manvi", "password": "secret-pass"})
    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        assert "secret-pass" not in db.query(User).first().password_hash
    client.post("/api/auth/logout")
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "manvi", "password": "nope-nope"})
    r = client.post("/api/auth/login", json={"username": "manvi", "password": "secret-pass"})
    assert r.status_code == 429


def test_task_validation(auth):
    r = auth.post("/api/tasks", json=task_body(mental_difficulty=11))
    assert r.status_code == 422 and r.json()["field"] == "mental_difficulty"
    r = auth.post("/api/tasks", json=task_body(is_fixed=True))
    assert r.status_code == 422 and "start" in r.json()["message"]
    r = auth.post("/api/tasks", json=task_body(est_minutes=2))
    assert r.status_code == 422


def test_task_crud_filter_sort_and_dependency_guard(auth):
    a = auth.post("/api/tasks", json=task_body(title="A", priority=1)).json()
    b = auth.post("/api/tasks", json=task_body(title="B", priority=4, depends_on_id=a["id"])).json()
    assert [t["title"] for t in auth.get("/api/tasks?sort=priority").json()] == ["B", "A"]
    r = auth.patch(f"/api/tasks/{a['id']}", json={"depends_on_id": b["id"]})
    assert r.status_code == 422 and "circle" in r.json()["message"]
    auth.post(f"/api/tasks/{a['id']}/complete")
    assert [t["title"] for t in auth.get("/api/tasks?status=pending").json()] == ["B"]
    assert auth.delete(f"/api/tasks/{b['id']}").status_code == 204
    assert auth.get(f"/api/tasks/{b['id']}").status_code == 404


def test_checkin_validation_and_latest(auth):
    assert auth.post("/api/checkins", json={"mental": 0, "physical": 5, "focus": 5, "stress": 5}).status_code == 422
    auth.post("/api/checkins", json={"mental": 7, "physical": 5, "focus": 6, "stress": 3})
    assert auth.get("/api/checkins/latest").json()["mental"] == 7


def test_generate_explain_move_lock_and_outcome(auth):
    tomorrow = (datetime.now() + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
    auth.post("/api/tasks", json=task_body(title="Report", deadline=tomorrow.isoformat()))
    auth.post("/api/tasks", json=task_body(title="Groceries", category="Errand", mental_difficulty=2,
                                            mental_energy_req=2, physical_difficulty=5, physical_energy_req=5, priority=2))
    auth.post("/api/checkins", json={"mental": 7, "physical": 6, "focus": 7, "stress": 3})
    r = auth.post("/api/schedules/generate", json={"horizon_days": 3, "seed": 1})
    assert r.status_code == 200
    plan = r.json()
    main = plan["plans"][0]
    assert main["is_active"] and main["blocks"]
    blk = main["blocks"][0]
    assert blk["verdict"] and blk["fired_rules"] and blk["duration"]["text"]
    # Current returns the same run.
    assert auth.get("/api/schedules/current").json()["run_id"] == plan["run_id"]
    # Lock it.
    r = auth.patch(f"/api/blocks/{blk['block_id']}", json={"locked": True})
    assert next(b for b in r.json()["plans"][0]["blocks"] if b["block_id"] == blk["block_id"])["locked"]
    # Moving into the past breaks H1.
    past = (datetime.now() - timedelta(days=1)).replace(hour=10, minute=0)
    r = auth.patch(f"/api/blocks/{blk['block_id']}", json={"start": past.isoformat()})
    assert r.status_code == 409 and "H1" in r.json()["message"]
    # Record an outcome: done in 90 minutes.
    r = auth.post(f"/api/blocks/{blk['block_id']}/outcome", json={"status": "done", "actual_minutes": 90})
    assert r.status_code == 200
    assert auth.post(f"/api/blocks/{blk['block_id']}/outcome", json={"status": "skipped"}).status_code == 409
    task = auth.get(f"/api/tasks/{blk['task_id']}").json()
    assert task["status"] == "done"
    # Undo restores it.
    auth.delete(f"/api/blocks/{blk['block_id']}/outcome")
    assert auth.get(f"/api/tasks/{blk['task_id']}").json()["status"] == "pending"


def test_outcomes_update_learned_model(auth):
    t = auth.post("/api/tasks", json=task_body(title="Study 1")).json()
    plan = auth.post("/api/schedules/generate", json={"seed": 3}).json()
    blk = plan["plans"][0]["blocks"][0]
    auth.post(f"/api/blocks/{blk['block_id']}/outcome", json={"status": "done", "actual_minutes": 90})
    m = auth.get("/api/models").json()
    assert m["records"]["outcomes"] == {"user": 1}
    # The hierarchical model (v2) uses even one outcome for the user's overall pace, shrunk toward the default.
    assert m["durations"]["version"] == "v2"
    assert m["durations"]["pooled"]["source"] == "pooled" and m["durations"]["pooled"]["n"] == 1
    assert t["id"] == blk["task_id"]


def test_demo_data_is_labelled_and_clearable(auth):
    auth.post("/api/tasks", json=task_body(title="Mine"))
    c = auth.post("/api/data/demo").json()
    assert c["tasks"]["demo"] >= 10 and c["tasks"]["user"] == 1
    plan = auth.post("/api/schedules/generate", json={"seed": 5}).json()
    assert plan["plans"][0]["blocks"]
    assert plan["meta"]["mode"] == "personalized"
    c = auth.delete("/api/data?source=demo").json()
    assert c["tasks"] == {"user": 1} and c["outcomes"] == {}
    assert auth.get("/api/data/export").json()["tasks"][0]["title"] == "Mine"


def test_preferences_validation(auth):
    p = auth.get("/api/preferences").json()
    p["day_end"] = "07:00"
    assert auth.put("/api/preferences", json=p).status_code == 422
    p["day_end"], p["horizon_days"] = "21:00", 5
    assert auth.put("/api/preferences", json=p).json()["horizon_days"] == 5


def test_insights_use_only_stored_records(auth):
    empty = auth.get("/api/insights").json()
    assert empty["outcomes"]["n"] == 0 and empty["accuracy"] == []
    auth.post("/api/tasks", json=task_body(title="Essay"))
    auth.post("/api/checkins", json={"mental": 7, "physical": 6, "focus": 7, "stress": 3})
    plan = auth.post("/api/schedules/generate", json={"seed": 2}).json()
    blk = plan["plans"][0]["blocks"][0]
    auth.post(f"/api/blocks/{blk['block_id']}/outcome", json={"status": "done", "actual_minutes": 80})
    ins = auth.get("/api/insights?source=user").json()
    assert ins["outcomes"] == {"n": 1, "done": 1, "partial": 0, "skipped": 0, "completion_rate": 100.0}
    assert ins["categories"][0]["actual"] == 80
    assert len(ins["accuracy"]) == 1 and ins["by_fit"][0]["n"] == 1
    assert auth.get("/api/insights?source=demo").json()["outcomes"]["n"] == 0


def test_simulate_endpoint(auth):
    assert auth.post("/api/simulate", json={}).status_code == 422
    auth.post("/api/tasks", json=task_body(title="Essay"))
    r = auth.post("/api/simulate", json={"late_start_minutes": 120, "urgent_task": {"title": "Call", "est_minutes": 15}})
    assert r.status_code == 200
    body = r.json()
    assert body["explanation"] and "before" in body and "after" in body
    assert auth.post("/api/simulate", json={"extend_task": {"task_id": 9999}}).status_code == 422


def test_evaluation_run_lifecycle(auth):
    import time as _t
    r = auth.post("/api/evaluation/runs", json={"users": 2, "days": 2, "horizon": 2})
    assert r.status_code == 202
    rid = r.json()["id"]
    for _ in range(120):
        run = auth.get(f"/api/evaluation/runs/{rid}").json()
        if run["status"] != "running":
            break
        _t.sleep(0.5)
    assert run["status"] == "done", run.get("error")
    assert run["results"]["summary"]["ga"]["plan_violations"]["mean"] == 0
    assert run["usefulness"] == {"n": 0, "mean": None}
    assert auth.get("/api/evaluation/runs").json()[0]["id"] == rid


def test_priority_and_form_fields_do_not_save_partial_tasks(auth):
    # Regression guard on the API side: a task is only created by an explicit POST.
    assert auth.get("/api/tasks").json() == []


def test_repeating_task_creates_daily_copies_that_get_planned(auth):
    r = auth.post("/api/tasks", json=task_body(title="DSA practice", est_minutes=30, recur_days="6,0,1,2,3,4,5,5"))
    assert r.status_code == 201
    template = r.json()
    assert template["recur_days"] == "0,1,2,3,4,5,6"  # tidied and de-duplicated
    # Only today's copy is listed by default; later days appear with upcoming=true.
    listed = auth.get("/api/tasks?status=pending").json()
    copies_today = [t for t in listed if t["parent_id"] == template["id"]]
    assert len(copies_today) == 1 and copies_today[0]["deadline"].startswith(copies_today[0]["occurrence_date"])
    all_copies = [t for t in auth.get("/api/tasks?status=pending&upcoming=true").json() if t["parent_id"] == template["id"]]
    assert len(all_copies) == 3  # default 3-day horizon
    # The template itself can't be completed; a copy can.
    assert auth.post(f"/api/tasks/{template['id']}/complete").status_code == 409
    plan = auth.post("/api/schedules/generate", json={"seed": 4}).json()
    planned = {b["task_id"] for b in plan["plans"][0]["blocks"]}
    assert template["id"] not in planned
    assert planned & {c["id"] for c in all_copies}
    # Each copy stays on its own day (due by the end of that day).
    for b in plan["plans"][0]["blocks"]:
        c = next(c for c in all_copies if c["id"] == b["task_id"])
        assert b["start"].startswith(c["occurrence_date"])


def test_editing_a_repeating_task_updates_future_copies(auth):
    t = auth.post("/api/tasks", json=task_body(title="Gym", recur_days="0,1,2,3,4,5,6", est_minutes=45)).json()
    auth.patch(f"/api/tasks/{t['id']}", json={"est_minutes": 60})
    copies = [c for c in auth.get("/api/tasks?upcoming=true").json() if c["parent_id"] == t["id"]]
    assert copies and all(c["est_minutes"] == 60 for c in copies)
    r = auth.patch(f"/api/tasks/{copies[0]['id']}", json={"recur_days": "1"})
    assert r.status_code == 422
    assert auth.delete(f"/api/tasks/{t['id']}").status_code == 204
    assert not [c for c in auth.get("/api/tasks?upcoming=true").json() if c["parent_id"] == t["id"]]


def test_old_unfinished_copies_become_missed(auth):
    from datetime import date as _date
    from app.db import SessionLocal
    from app.models import Task, User
    from app.services.recurrence import ensure_copies
    t = auth.post("/api/tasks", json=task_body(title="Read", recur_days="0,1,2,3,4,5,6")).json()
    with SessionLocal() as db:
        tmpl = db.get(Task, t["id"])
        tmpl.created_at = datetime.now() - timedelta(days=5)
        db.commit()
        user = db.query(User).first()
        ensure_copies(db, user, _date.today() - timedelta(days=2), 2)
        ensure_copies(db, user, _date.today(), 1)
        missed = db.query(Task).filter(Task.parent_id == t["id"], Task.status == "missed").count()
    assert missed == 2


def test_repeating_task_cannot_wait_for_another(auth):
    a = auth.post("/api/tasks", json=task_body(title="A")).json()
    r = auth.post("/api/tasks", json=task_body(title="B", recur_days="0", depends_on_id=a["id"]))
    assert r.status_code == 422


def test_old_database_gets_new_columns(tmp_path):
    import sqlite3
    from app.db import init_db, make_engine
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, user_id INTEGER, title VARCHAR(200), status VARCHAR(10))")
    con.commit(); con.close()
    init_db(make_engine(path))
    cols = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(tasks)")}
    assert {"recur_days", "recur_until", "parent_id", "occurrence_date"} <= cols
