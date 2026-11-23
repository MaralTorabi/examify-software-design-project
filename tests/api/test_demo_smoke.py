"""Full offline classroom demo using an isolated database."""
from pathlib import Path
from runpy import run_path

from fastapi.testclient import TestClient

from api.bootstrap import create_app
from core.config import Settings


def test_demo_smoke(tmp_path):
    helpers = run_path(str(Path(__file__).with_name("test_api_routes.py")))
    with TestClient(create_app(Settings(offline_mode=True), database_path=tmp_path / "demo.db")) as client:
        assert client.get("/").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        owner = helpers["account"](client, "demo@example.com")
        helpers["test_exam_adapts_retries_and_reports"](client, owner)
