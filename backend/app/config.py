"""Runtime settings. Everything is local; no API keys are needed for the baseline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BACKEND_DIR / "fixtures"
DEFAULT_DATA_DIR = BACKEND_DIR / "var"


@dataclass(frozen=True)
class Settings:
    """Where the runtime SQLite DB and runtime copies of source CSVs live.

    The committed fixtures in ``backend/fixtures`` are never modified at runtime:
    seeding copies them into ``data_dir/sources`` (git-ignored) so demo edits and
    tests cannot mutate the repository's synthetic data.
    """

    data_dir: Path
    fixtures_dir: Path = FIXTURES_DIR
    receiver_mode: str = "local_demo"  # "local_demo" or "fail" (local failing receiver)
    session_ttl_seconds: int = 8 * 60 * 60

    @property
    def db_path(self) -> Path:
        return self.data_dir / "datagate.sqlite3"

    @property
    def sources_dir(self) -> Path:
        return self.data_dir / "sources"


def settings_from_env() -> Settings:
    data_dir = Path(os.environ.get("DATAGATE_DATA_DIR", str(DEFAULT_DATA_DIR))).resolve()
    receiver_mode = os.environ.get("DATAGATE_RECEIVER", "local_demo")
    return Settings(data_dir=data_dir, receiver_mode=receiver_mode)
