"""Shared fixtures. Every test gets its own temporary DB + source copies, so the
team's demo database (backend/var) is never touched by tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.receiver import FailingReceiver, LocalCapturingReceiver  # noqa: E402

PREVIEW_A = {"dataset_id": "feedback_a", "purpose": "feedback_summary", "destination": "demo_receiver"}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
def receiver() -> LocalCapturingReceiver:
    return LocalCapturingReceiver()


@pytest.fixture
def app(settings, receiver):
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
