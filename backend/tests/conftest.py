"""Shared fixtures. Every test gets its own temporary DB + source copies, so the
team's demo database (backend/var) is never touched by tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DEFAULT_DATA_DIR, Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.receiver import FailingReceiver, LocalCapturingReceiver  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "scenario(*ids): security evidence scenario ids (SEC-xx), see app/evidence.py")


@pytest.fixture(autouse=True)
def _never_touch_runtime_data(tmp_path_factory, monkeypatch):
    """Guard: even if a developer exported DATAGATE_DATA_DIR=backend/var, anything that reads
    the environment during a test (e.g. the owner CLI) gets throwaway storage unless the test
    deliberately points it at its own temporary directory."""
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(tmp_path_factory.mktemp("env-data")))
    monkeypatch.delenv("DATAGATE_RECEIVER", raising=False)


def _assert_isolated(data_dir: Path) -> None:
    runtime = DEFAULT_DATA_DIR.resolve()
    resolved = data_dir.resolve()
    if resolved == runtime or runtime in resolved.parents:
        raise RuntimeError("Tests must not use the runtime demo data directory (backend/var).")


PREVIEW_A = {"dataset_id": "feedback_a", "purpose": "feedback_summary", "destination": "demo_receiver"}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(data_dir=tmp_path / "data")
    _assert_isolated(s.data_dir)
    return s


@pytest.fixture
def receiver() -> LocalCapturingReceiver:
    return LocalCapturingReceiver()


@pytest.fixture
def app(settings, receiver):
    _assert_isolated(settings.data_dir)
    return create_app(settings, receiver)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def login(client: TestClient, account_id: str) -> dict[str, str]:
    resp = client.post("/api/demo/session", json={"account_id": account_id})
    assert resp.status_code == 200, resp.text
    return {"Authorization": "Bearer " + resp.json()["token"]}


@pytest.fixture
def a(client) -> dict[str, str]:
    return login(client, "analyst_a")


@pytest.fixture
def b(client) -> dict[str, str]:
    return login(client, "analyst_b")


def preview(client, headers, body=None):
    return client.post("/api/requests/preview", headers=headers, json=body or PREVIEW_A)


def send(client, headers, p, **overrides):
    body = {"approve": True, "expected_review_revision": p["review_revision"], "preview_hash": p["preview_hash"]}
    body.update(overrides)
    return client.post(f"/api/requests/{p['request_id']}/send", headers=headers, json=body)


def failing_client(settings) -> tuple[TestClient, FailingReceiver]:
    rec = FailingReceiver()
    return TestClient(create_app(settings, rec)), rec
