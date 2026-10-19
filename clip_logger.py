"""Per-clip run log with snapshots of generated artifacts."""

from __future__ import annotations

import hashlib
import json
import traceback
import uuid
from datetime import datetime
from pathlib import Path


TEXT_EXTENSIONS = {
    ".txt", ".ass", ".srt", ".vtt", ".md", ".csv", ".xml", ".log",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ClipRunLogger:
    """Writes one log.json per clip folder and keeps a snapshot for each run."""

    def __init__(
        self,
        clip_dir: str | Path,
        *,
        title: str,
        mode: str,
        input_value: str,
        duration_target: int | None = None,
    ) -> None:
        self.clip_dir = Path(clip_dir)
        self.clip_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.clip_dir / "log.json"

        if self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.data = {}
        else:
            self.data = {}

        if not isinstance(self.data, dict) or not isinstance(self.data.get("runs"), list):
            self.data = {"schema_version": 1, "runs": []}
        self.data.setdefault("schema_version", 1)

        self.run = {
            "run_id": str(uuid.uuid4()),
            "started_at": _now(),
            "finished_at": None,
            "status": "running",
            "title": title,
            "mode": mode,
            "input": input_value,
            "duration_target_seconds": duration_target,
            "events": [{"at": _now(), "event": "generation_started"}],
            "error": None,
            "artifacts": [],
        }
        self.data["runs"].append(self.run)
        self._write()

    def finish(self, status: str, error: BaseException | None = None) -> None:
        self.run["finished_at"] = _now()
        self.run["status"] = status
        event_name = {
            "completed": "generation_completed",
            "failed": "generation_failed",
            "existing_snapshot": "existing_artifacts_snapshotted",
        }.get(status, f"generation_{status}")
        self.run["events"].append({
            "at": self.run["finished_at"],
            "event": event_name,
        })
        if error is not None:
            self.run["error"] = {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": "".join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                ),
            }
        self.run["artifacts"] = self._snapshot_artifacts()
        self._write()

    def _snapshot_artifacts(self) -> list[dict]:
        artifacts = []
        for path in sorted(self.clip_dir.rglob("*")):
            if not path.is_file() or path == self.path:
                continue
            try:
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                relative = path.relative_to(self.clip_dir).as_posix()
                item = {
                    "path": relative,
                    "size_bytes": path.stat().st_size,
                    "sha256": digest.hexdigest(),
                    "type": path.suffix.lower().lstrip(".") or "file",
                }

                if path.suffix.lower() == ".json":
                    try:
                        raw = path.read_bytes()
                        item["content"] = json.loads(raw.decode("utf-8-sig"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        item["content_text"] = path.read_text(
                            encoding="utf-8", errors="replace"
                        )
                elif path.suffix.lower() in TEXT_EXTENSIONS:
                    item["content_text"] = path.read_text(
                        encoding="utf-8-sig", errors="replace"
                    )

                artifacts.append(item)
            except OSError as exc:
                artifacts.append({
                    "path": path.relative_to(self.clip_dir).as_posix(),
                    "snapshot_error": str(exc),
                })
        return artifacts

    def _write(self) -> None:
        temporary = self.path.with_name("log.json.tmp")
        temporary.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)
