from __future__ import annotations

from pathlib import Path

from harbormaster.config import data_dir
from harbormaster.storage.base import ObjectRef


class LocalObjectStore:
    backend = "local"

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else data_dir() / "objects"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        clean = key.replace("\\", "/").lstrip("/")
        if ".." in Path(clean).parts:
            raise ValueError("invalid object key")
        path = (self.root / clean).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError("invalid object key") from exc
        return path

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> ObjectRef:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return ObjectRef(
            key=key,
            backend=self.backend,
            bytes=len(data),
            content_type=content_type,
            uri=str(path),
        )

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def health(self) -> dict:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / ".health"
            probe.write_text("ok", encoding="utf-8")
            ok = probe.read_text(encoding="utf-8") == "ok"
            return {
                "ok": ok,
                "backend": self.backend,
                "root": str(self.root),
                "error": "" if ok else "write probe failed",
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "backend": self.backend, "root": str(self.root), "error": str(exc)[:200]}
