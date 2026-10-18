"""Receiver adapter boundary. EVERY outbound dispatch goes through ``send``.

The baseline ships a local capturing receiver. It really receives the prepared
canonical bytes and returns a plainly labeled acknowledgement. It is NOT an AI
model and produces no analysis.

To add a real provider later (layer L4), implement ``ReceiverAdapter`` and
select it in ``build_receiver``; do not call providers from anywhere else.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ReceiverResult:
    mode: str
    acknowledged: bool
    message_count: int
    note: str

    def as_dict(self) -> dict:
        return {"mode": self.mode, "acknowledged": self.acknowledged, "message_count": self.message_count, "note": self.note}


class ReceiverAdapter(Protocol):
    mode: str

    def send(self, request_id: str, payload_bytes: bytes) -> ReceiverResult: ...


@dataclass
class LocalCapturingReceiver:
    """Captures bytes in memory, per request. No public endpoint exposes captures."""

    mode: str = "local_demo"
    invocations: list[tuple[str, bytes]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def send(self, request_id: str, payload_bytes: bytes) -> ReceiverResult:
        with self._lock:
            self.invocations.append((request_id, bytes(payload_bytes)))
        count = len(json.loads(payload_bytes.decode("utf-8"))["messages"])
        return ReceiverResult(
            mode=self.mode,
            acknowledged=True,
            message_count=count,
            note="Local test receiver; no external AI model was called.",
        )


@dataclass
class FailingReceiver:
    """Local receiver that records the invocation and then fails (for demos/tests)."""

    mode: str = "local_demo"
    invocations: list[tuple[str, bytes]] = field(default_factory=list)

    def send(self, request_id: str, payload_bytes: bytes) -> ReceiverResult:
        self.invocations.append((request_id, bytes(payload_bytes)))
        raise RuntimeError("local demo receiver configured to fail")


def build_receiver(mode: str) -> ReceiverAdapter:
    if mode == "fail":
        return FailingReceiver()
    return LocalCapturingReceiver()
