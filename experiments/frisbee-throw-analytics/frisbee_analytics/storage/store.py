"""Persistent local storage of analysed throws.

Sessions are stored as one JSON file per session under a data directory
(default ``~/.frisbee_analytics``). JSON keeps the store human-inspectable
and diff-friendly; the volume of data (a few hundred points per throw) is
far too small to need a database.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..models import ThrowRecord

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class SessionStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else Path.home() / ".frisbee_analytics"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_name: str) -> Path:
        safe = _SAFE_NAME.sub("_", session_name)
        safe = re.sub(r"\.{2,}", "_", safe).strip("_.") or "session"
        return self.root / f"{safe}.json"

    def list_sessions(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))

    def load_session(self, session_name: str) -> list[ThrowRecord]:
        path = self._path(session_name)
        if not path.exists():
            return []
        data = json.loads(path.read_text())
        return [ThrowRecord.from_dict(item) for item in data.get("throws", [])]

    def save_throw(self, session_name: str, record: ThrowRecord) -> None:
        throws = self.load_session(session_name)
        throws.append(record)
        self._write(session_name, throws)

    def delete_session(self, session_name: str) -> None:
        self._path(session_name).unlink(missing_ok=True)

    def _write(self, session_name: str, throws: list[ThrowRecord]) -> None:
        payload = {
            "session": session_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "throws": [t.to_dict() for t in throws],
        }
        self._path(session_name).write_text(json.dumps(payload, indent=2))
