"""FastAPI application: thin HTTP layer over ``workflow.Workflow``.

Run (one worker):  uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import SessionStore, current_account
from .config import Settings, settings_from_env
from .errors import ApiError, install_error_handlers
from .receiver import ReceiverAdapter, build_receiver
from .schemas import PreviewBody, ReviewBody, SendBody, SessionBody
from .seed import seed
from .workflow import Workflow


def create_app(settings: Settings | None = None, receiver: ReceiverAdapter | None = None) -> FastAPI:
    settings = settings or settings_from_env()
    store = seed(settings)  # idempotent: seeds an empty DB, never overwrites owner edits
    receiver = receiver or build_receiver(settings.receiver_mode)

    app = FastAPI(title="DataGate", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.settings = settings
    app.state.store = store
    app.state.sessions = SessionStore(settings.session_ttl_seconds)
    app.state.receiver = receiver
    app.state.workflow = Workflow(store, settings.sources_dir, receiver)
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def wf() -> Workflow:
        return app.state.workflow

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "receiver_mode": receiver.mode, "authentication_mode": "demo"}

    @app.post("/api/demo/session")
    def demo_session(body: SessionBody) -> dict:
        account = store.get_account(body.account_id)
        if account is None:
            raise ApiError("INVALID_REQUEST", message="Unknown demo account.")
        return {
            "token": app.state.sessions.issue(account["account_id"]),
            "token_type": "bearer",
            "account": {"account_id": account["account_id"], "display_name": account["display_name"]},
            "authentication_mode": "demo",
        }

    @app.get("/api/datasets")
    def datasets(account_id: str = Depends(current_account)) -> dict:
        return wf().list_datasets(account_id)

    @app.post("/api/requests/preview")
    def preview(body: PreviewBody, account_id: str = Depends(current_account)) -> dict:
        return wf().create_preview(account_id, body.dataset_id, body.purpose, body.destination)

    @app.patch("/api/requests/{request_id}/review")
    def review(request_id: str, body: ReviewBody, account_id: str = Depends(current_account)) -> dict:
        custom = None if body.custom_redactions is None else [(c.message_index, c.start, c.end) for c in body.custom_redactions]
        return wf().review(account_id, request_id, body.expected_review_revision, body.hide_message_indices, custom)

    @app.post("/api/requests/{request_id}/send")
    def send(request_id: str, body: SendBody, account_id: str = Depends(current_account)) -> dict:
        return wf().send(account_id, request_id, body.expected_review_revision, body.preview_hash)

    @app.get("/api/requests/{request_id}/receipt")
    def receipt(request_id: str, account_id: str = Depends(current_account)) -> dict:
        return wf().receipt(account_id, request_id)

    return app

