"""API for the new options: optimiser choice, stability-aware replanning, robustness and the lab studies."""
from .test_api import task_body


def _plan(auth, **body):
    r = auth.post("/api/schedules/generate", json={"seed": 3, **body})
    assert r.status_code == 200, r.text
    return r.json()


def test_preferences_store_optimizer_and_stability(auth):
    p = auth.get("/api/preferences").json()
    assert p["optimizer"] == "hybrid" and p["replan_stability"] == 0.5
    p.update(optimizer="ga", replan_stability=0.9)
    assert auth.put("/api/preferences", json=p).json()["optimizer"] == "ga"
    p["replan_stability"] = 1.5
    assert auth.put("/api/preferences", json=p).status_code == 422


def test_generate_reports_optimizer_and_robustness(auth):
    for i in range(4):
        auth.post("/api/tasks", json=task_body(title=f"T{i}"))
    out = _plan(auth, optimizer="ga")
    main = out["plans"][0]
    assert main["optimizer"] == "ga"
    assert main["robustness"]["runs"] > 0 and 0 <= main["robustness"]["p_overrun_any_day"] <= 1
    assert "tradeoffs" in main


def test_regenerating_keeps_the_plan_when_stability_is_high(auth):
    for i in range(5):
        auth.post("/api/tasks", json=task_body(title=f"T{i}"))
    first = _plan(auth)
    starts = {b["task_id"]: b["start"] for b in first["plans"][0]["blocks"]}
    again = _plan(auth, seed=99, stability=1.0)  # a different seed would normally reshuffle
    st = again["plans"][0]["stability"]
    assert st["previous_blocks"] == len(starts)
    kept = sum(1 for b in again["plans"][0]["blocks"] if starts.get(b["task_id"]) == b["start"])
    assert kept == st["kept"] and st["kept"] >= len(starts) - 1


def test_whatif_accepts_a_stability_level(auth):
    for i in range(4):
        auth.post("/api/tasks", json=task_body(title=f"T{i}"))
    _plan(auth)
    r = auth.post("/api/simulate", json={"urgent_task": {"title": "Now", "est_minutes": 45}, "stability": 0.7})
    assert r.status_code == 200
    body = r.json()
    assert body["stability"] == 0.7 and "free_replan" in body
    bad = auth.post("/api/simulate", json={"late_start_minutes": 30, "stability": 2})
    assert bad.status_code == 422
