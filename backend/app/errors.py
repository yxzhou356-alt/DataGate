"""Stable error envelope (API_CONTRACT.md section 10).

Error messages are fixed strings: they never echo tokens, source rows or
submitted values.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# code -> (http status, message, suggested action)
ERRORS: dict[str, tuple[int, str, str]] = {
    "AUTH_REQUIRED": (401, "A demo session token is required.", "Select a demo account first."),
    "INVALID_SESSION": (401, "The session token is invalid or expired.", "Select a demo account again."),
    "DATASET_NOT_FOUND": (404, "Dataset not found.", "Choose a dataset from your list."),
    "DATASET_ACCESS_DENIED": (403, "You are not permitted to use this dataset.", "Choose another dataset or contact its owner."),
    "REQUEST_NOT_FOUND": (404, "Request not found.", "Create a new preview."),
    "REQUEST_ACCESS_DENIED": (403, "This request belongs to another account.", "Use your own requests."),
    "PURPOSE_NOT_ALLOWED": (403, "The owner policy does not allow this purpose.", "Choose an allowed purpose."),
    "DESTINATION_NOT_ALLOWED": (403, "The owner policy does not allow this destination.", "Choose an allowed destination."),
    "SHARING_PROHIBITED": (403, "The owner policy prohibits sharing this dataset.", "Contact the dataset owner."),
    "DATASET_INVALID": (422, "The source dataset failed validation.", "Ask the dataset owner to fix the source."),
    "INVALID_REQUEST": (422, "The request body is invalid.", "Check the request fields."),
    "INVALID_REVIEW": (422, "The review choices are invalid.", "Choose valid message positions."),
    "NO_CONTENT_TO_SEND": (422, "All messages would be hidden; nothing would be sent.", "Keep at least one message visible."),
    "REVIEW_CHANGED": (409, "The review revision changed.", "Reload the latest preview and review it again."),
    "PREVIEW_CHANGED": (409, "The preview content changed.", "Review the latest preview before sending."),
    "DATASET_CHANGED": (409, "The source dataset changed after the preview.", "Create a new preview."),
    "POLICY_CHANGED": (409, "The owner policy changed after the preview.", "Create a new preview."),
    "ACCESS_REVOKED": (403, "Dataset access is no longer permitted.", "Choose another dataset or contact its owner."),
    "ALREADY_DISPATCHED": (409, "This request was already dispatched.", "Create a new preview to send again."),
    "REQUEST_NOT_READY": (409, "This request is not ready for that action.", "Create a new preview."),
    "RECEIPT_NOT_READY": (409, "No final outcome exists yet for this request.", "Send or finish the request first."),
    "RECEIVER_FAILED": (502, "The receiver did not confirm delivery.", "Create a new reviewed request to try again."),
    "NOT_FOUND": (404, "Route not found.", "Check the API path."),
}


class ApiError(Exception):
    def __init__(self, code: str, request_id: str | None = None, message: str | None = None):
        status, default_message, action = ERRORS[code]
        self.code = code
        self.status = status
        self.message = message or default_message
        self.action = action
        self.request_id = request_id
        super().__init__(code)


def envelope(code: str, message: str, action: str, request_id: str | None) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id, "action": action}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=envelope(exc.code, exc.message, exc.action, exc.request_id))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, __: RequestValidationError) -> JSONResponse:
        # Deliberately do not include FastAPI's default detail: it echoes input values.
        status, message, action = ERRORS["INVALID_REQUEST"]
        return JSONResponse(status_code=status, content=envelope("INVALID_REQUEST", message, action, None))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            status, message, action = ERRORS["NOT_FOUND"]
            return JSONResponse(status_code=404, content=envelope("NOT_FOUND", message, action, None))
        if exc.status_code == 405:
            return JSONResponse(status_code=405, content=envelope("INVALID_REQUEST", "Method not allowed.", "Check the API method.", None))
        return JSONResponse(status_code=exc.status_code, content=envelope("INVALID_REQUEST", "Request failed.", "Check the request.", None))
