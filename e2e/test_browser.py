"""Browser end-to-end test: the whole planner through its real UI.

Starts the backend (which serves the built frontend) on a free port with a throwaway
database, then drives Chrome or Chromium through: first-run account, demo week,
planning, the explanation of a block, the Advanced settings and the calibration card.

Run (after `npm run build` in frontend/):
    pip install -r e2e/requirements.txt
    python -m pytest e2e -q
Set CHROME_PATH to use an installed Chrome instead of Playwright's own browser
(`python -m playwright install chromium`).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        pytest.skip("Build the frontend first: cd frontend && npm run build")
    port = _free_port()
    tmp = tempfile.mkdtemp()
    env = {**os.environ, "EAP_DB_PATH": str(Path(tmp) / "e2e.db")}
    python = os.environ.get("BACKEND_PYTHON", sys.executable)
    proc = subprocess.Popen([python, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=BACKEND, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("backend did not start")
    yield url
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="module")
def page(server):
    with sync_playwright() as pw:
        exe = os.environ.get("CHROME_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        pg.set_default_timeout(60_000)
        pg.goto(server)
        pg.base = server  # type: ignore[attr-defined]
        yield pg
        browser.close()


def test_first_run_demo_plan_and_explanation(page):
    page.get_by_label("Name").fill("pilot")
    page.get_by_label("Password", exact=True).fill("pilot-pass-1")
    page.get_by_label("Confirm password").fill("pilot-pass-1")
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("link", name="Settings")).to_be_visible()

    page.get_by_role("link", name="Settings").click()
    page.get_by_role("button", name="Load demo week").click()
    expect(page.get_by_text("Demo week loaded")).to_be_visible()
    # The optimiser and simulation controls live under Advanced.
    page.get_by_text("Advanced").click()
    page.get_by_label("Risk simulation").select_option("quick")
    page.get_by_role("button", name="Save settings").click()
    expect(page.get_by_text("Settings saved")).to_be_visible()
    expect(page.get_by_text("Will a planned block happen?")).to_be_visible()

    page.goto(page.base + "/schedule")
    page.get_by_role("button", name="Plan my days").click()
    block = page.locator("[aria-label*='to happen']").first
    expect(block).to_be_visible()
    block.click()
    expect(page.get_by_text("Chance it happens at this time")).to_be_visible()
    expect(page.get_by_text("Likely range")).to_be_visible()


def test_calibration_card_on_insights(page):
    page.goto(page.base + "/insights")
    expect(page.get_by_text("Are the predictions honest?")).to_be_visible()
