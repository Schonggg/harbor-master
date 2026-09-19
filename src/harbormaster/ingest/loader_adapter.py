"""Inbox adapter — remote sponsor API first, local data/inbox fallback."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import httpx

from harbormaster.config import bundle_dir, cache_dir, data_dir, get_settings
from harbormaster.models import AttachmentRef, EmailMessage, is_demo_email_id


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in (None,):
        _ = fmt
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _attachment_refs(raw: Any) -> list[AttachmentRef]:
    refs: list[AttachmentRef] = []
    for item in _as_list(raw):
        if isinstance(item, str):
            name = Path(item).name
            refs.append(AttachmentRef(path=item, filename=name, kind_hint=_kind_hint(name)))
            continue
        if not isinstance(item, dict):
            continue
        path = _as_str(
            item.get("path")
            or item.get("url")
            or item.get("filename")
            or item.get("name")
            or item.get("id")
        )
        filename = _as_str(item.get("filename") or item.get("name") or Path(path).name)
        mime = _as_str(item.get("mime") or item.get("content_type") or item.get("type"))
        kind = item.get("kind") or item.get("doc_type") or _kind_hint(filename or path)
        refs.append(
            AttachmentRef(
                path=path,
                filename=filename,
                mime=mime,
                kind_hint=str(kind) if kind else None,
            )
        )
    return refs


def _kind_hint(name: str) -> str | None:
    n = name.lower()
    if any(tok in n for tok in ("shipping_instruction", "shipping-instruction", "_si.", "-si.", " si.")):
        return "si"
    if n.startswith("si.") or n.startswith("si_") or "/si/" in n.replace("\\", "/"):
        return "si"
    if "bill_of_lading" in n or "bill-of-lading" in n or "_bl." in n or "-bl." in n:
        return "bl"
    if "draft_bl" in n or "bl_draft" in n or "bol" in n:
        return "bl"
    if n.startswith("bl.") or n.startswith("bl_"):
        return "bl"
    if "shipping instruction" in n or n.endswith("si.txt") or n.endswith("si.pdf") or n.endswith("si.docx"):
        return "si"
    if n.endswith("bl.txt") or n.endswith("bl.pdf") or n.endswith("bl.docx"):
        return "bl"
    return None


def coerce_email(data: dict[str, Any], email_id: str | None = None) -> EmailMessage:
    eid = _as_str(
        email_id
        or data.get("email_id")
        or data.get("id")
        or data.get("message_id")
        or data.get("emailId")
    )
    body = _as_str(
        data.get("body_text")
        or data.get("body")
        or data.get("text")
        or data.get("content")
        or data.get("snippet")
    )
    to_raw = data.get("to_addrs") or data.get("to") or data.get("recipients") or []
    to_addrs = [_as_str(x) for x in _as_list(to_raw) if x]
    attachments = _attachment_refs(
        data.get("attachments") or data.get("attachment_paths") or data.get("files")
    )
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    return EmailMessage(
        email_id=eid,
        subject=_as_str(data.get("subject")),
        body_text=body,
        from_addr=_as_str(data.get("from_addr") or data.get("from") or data.get("sender")),
        to_addrs=to_addrs,
        received_at=_parse_dt(data.get("received_at") or data.get("date") or data.get("timestamp")),
        attachment_paths=[a.local_path or a.path for a in attachments if a.path],
        attachments=attachments,
        meta=meta,
    )


def _unwrap_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("emails", "items", "data", "results", "records"):
            if isinstance(payload.get(key), list):
                return payload[key]
        # id → record mapping
        if payload and all(isinstance(v, dict) for v in payload.values()):
            rows = []
            for key, val in payload.items():
                row = dict(val)
                row.setdefault("email_id", key)
                rows.append(row)
            return rows
    return []


class InboxError(RuntimeError):
    pass


class LoaderAdapter:
    """Hosted Supabase inbox first; local bundle only if the cloud table is empty."""

    def __init__(self, inbox: Path | None = None, *, base_url: str | None = None) -> None:
        settings = get_settings()
        self.inbox = inbox or (data_dir() / "inbox")
        self.bundle = bundle_dir()
        self.official_inbox = (self.bundle / "inbox") if self.bundle else None
        self.base_url = (base_url or settings.inbox_base_url or "").rstrip("/")
        self.timeout = settings.inbox_timeout_s
        self._remote_ok: bool | None = None
        self._id_cache: list[str] | None = None
        self._sample: dict[str, Any] | None = None
        self._cloud_id_cache: list[str] | None = None

    def inbox_reachable(self) -> bool:
        if self._remote_ok is not None:
            return self._remote_ok
        if not self.base_url:
            self._remote_ok = False
            return False
        try:
            with httpx.Client(timeout=min(self.timeout, 0.5)) as client:
                resp = client.get(urljoin(self.base_url + "/", "emails"))
                self._remote_ok = resp.status_code < 500
        except httpx.HTTPError:
            self._remote_ok = False
        return self._remote_ok

    def _get(self, path: str, *, params: dict | None = None) -> httpx.Response:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp

    def _post(self, path: str, payload: Any) -> httpx.Response:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        with httpx.Client(timeout=max(self.timeout, 60.0), follow_redirects=True) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp

    def list_email_ids(self, *, source: str = "auto") -> list[str]:
        if source == "local":
            return self._list_folder(self.inbox)
        if source == "official":
            return self._list_official()
        if source == "remote":
            return self._list_remote()
        cloud = self._cloud_ids()
        if cloud:
            return list(cloud)
        if self.inbox_reachable():
            return self._list_remote()
        return self._merge_ids(self._list_official(), self._list_folder(self.inbox))

    def _list_folder(self, folder: Path | None) -> list[str]:
        if not folder or not folder.exists():
            return []
        ids = [p.stem for p in sorted(folder.glob("email_*.json"))]
        ids.extend(p.stem for p in sorted(folder.glob("demo_*.json")) if p.stem not in ids)
        ids.extend(p.stem for p in sorted(folder.glob("*.eml")) if p.stem not in ids)
        if not ids:
            ids = [p.stem for p in sorted(folder.glob("*.json"))]
        return ids

    def _cloud_ids(self) -> list[str]:
        if self._cloud_id_cache is not None:
            return self._cloud_id_cache
        try:
            from harbormaster.ledger.store import LedgerStore

            self._cloud_id_cache = LedgerStore().list_inbox_ids()
        except Exception:
            self._cloud_id_cache = []
        return self._cloud_id_cache

    def _list_official(self) -> list[str]:
        cloud = self._cloud_ids()
        if cloud:
            return cloud
        return self._list_folder(self.official_inbox)

    def _merge_ids(self, *groups: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for eid in group:
                if eid and eid not in seen:
                    seen.add(eid)
                    out.append(eid)
        return out

    def _list_local(self) -> list[str]:
        return self._list_folder(self.inbox)

    def _list_remote(self) -> list[str]:
        if self._id_cache is not None:
            return list(self._id_cache)
        rows = self._fetch_all_email_rows()
        ids: list[str] = []
        seen: set[str] = set()
        for row in rows:
            if isinstance(row, dict):
                eid = _as_str(row.get("email_id") or row.get("id") or row.get("message_id"))
            else:
                eid = _as_str(row)
            if eid and eid not in seen:
                seen.add(eid)
                ids.append(eid)
        self._id_cache = ids
        return list(ids)

    def _fetch_all_email_rows(self) -> list[Any]:
        rows: list[Any] = []
        offset = 0
        page = 1
        while True:
            try:
                resp = self._get("emails", params={"offset": offset, "limit": 200, "page": page})
            except httpx.HTTPError as exc:
                if offset == 0 and page == 1:
                    raise InboxError(f"GET /emails failed: {exc}") from exc
                break
            chunk = _unwrap_list(resp.json())
            if not chunk:
                break
            rows.extend(chunk)
            if len(chunk) < 200:
                break
            offset += len(chunk)
            page += 1
            if page > 50:
                break
        return rows

    def load(self, email_id: str, *, source: str = "auto") -> EmailMessage:
        if source in {"official", "auto"}:
            cloud = self._load_cloud(email_id)
            if cloud is not None:
                return cloud
        if source in {"local", "official", "auto"}:
            local = self._load_local(email_id)
            if local is not None:
                return local
        if source not in {"local", "official"} and (source == "remote" or self.inbox_reachable()):
            return self._load_remote(email_id)
        raise FileNotFoundError(f"email not found: {email_id}")

    def _load_local(self, email_id: str) -> EmailMessage | None:
        folders = [self.inbox]
        # Disk bundle is upload-only once the hosted inbox exists.
        if self.official_inbox and not self._cloud_ids():
            folders.append(self.official_inbox)
        for folder in folders:
            json_path = folder / f"{email_id}.json"
            if not json_path.exists():
                continue
            data = json.loads(json_path.read_text(encoding="utf-8"))
            email = coerce_email(data, email_id)
            email.attachment_paths = [
                str(self._resolve_local_attachment(p)) for p in email.attachment_paths
            ]
            for att in email.attachments:
                att.local_path = str(self._resolve_local_attachment(att.local_path or att.path))
            return email
        eml_path = self.inbox / f"{email_id}.eml"
        if eml_path.exists():
            text = eml_path.read_text(encoding="utf-8", errors="replace")
            subject = ""
            for line in text.splitlines():
                if line.lower().startswith("subject:"):
                    subject = line.split(":", 1)[1].strip()
                    break
            return EmailMessage(email_id=email_id, subject=subject, body_text=text)
        return None

    def _load_cloud(self, email_id: str) -> EmailMessage | None:
        try:
            from harbormaster.ledger.store import LedgerStore

            row = LedgerStore().get_inbox_email(email_id)
        except Exception:
            return None
        if not row:
            return None
        payload = dict(row.get("payload") or {})
        payload.setdefault("email_id", email_id)
        payload.setdefault("subject", row.get("subject") or "")
        payload.setdefault("from", row.get("from_addr") or payload.get("from") or "")
        payload.setdefault("body", row.get("body_text") or payload.get("body") or "")
        email = coerce_email(payload, email_id)
        dest = cache_dir() / "cloud_inbox" / email_id
        dest.mkdir(parents=True, exist_ok=True)
        refs: list[AttachmentRef] = []
        paths: list[str] = []
        for att in row.get("attachments") or []:
            if not isinstance(att, dict):
                continue
            filename = _as_str(att.get("filename") or att.get("name") or "attachment.txt")
            text = _as_str(att.get("text"))
            safe = Path(filename).name or "attachment.txt"
            stem = Path(safe).stem or "attachment"
            out = dest / f"{stem}.txt"
            out.write_text(text, encoding="utf-8")
            refs.append(
                AttachmentRef(
                    path=str(out),
                    filename=filename,
                    local_path=str(out),
                    kind_hint=_as_str(att.get("kind_hint")) or _kind_hint(filename),
                )
            )
            paths.append(str(out))
        email.attachments = refs
        email.attachment_paths = paths
        email.meta = {**(email.meta or {}), "source": "supabase"}
        return email

    def _resolve_local_attachment(self, path_str: str) -> Path:
        path = Path(path_str)
        if path.is_file():
            return path
        roots: list[Path] = []
        if self.bundle:
            roots.append(self.bundle)
        roots.extend([self.inbox, data_dir()])
        if self.inbox.parent:
            roots.append(self.inbox.parent)
        for root in roots:
            candidate = root / path_str
            if candidate.is_file():
                return candidate
            named = root / "attachments" / Path(path_str).name
            if named.is_file():
                return named
        return path

    def _load_remote(self, email_id: str) -> EmailMessage:
        try:
            resp = self._get(f"emails/{quote(str(email_id), safe='')}")
        except httpx.HTTPError as exc:
            raise FileNotFoundError(f"email not found: {email_id}") from exc
        data = resp.json()
        if isinstance(data, dict) and isinstance(data.get("email"), dict):
            data = data["email"]
        email = coerce_email(data if isinstance(data, dict) else {"body": str(data)}, email_id)
        materialized: list[str] = []
        for att in email.attachments:
            local = self.download_attachment(att.path, filename=att.filename)
            att.local_path = str(local)
            materialized.append(str(local))
        email.attachment_paths = materialized
        return email

    def download_attachment(self, path: str, filename: str = "") -> Path:
        if not path:
            raise FileNotFoundError("empty attachment path")
        local = Path(path)
        if local.is_file():
            return local
        dest_dir = cache_dir() / "attachments"
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = (filename or Path(path).name or "attachment").replace("/", "_").replace("\\", "_")
        digest = quote(path, safe="")[:80]
        dest = dest_dir / f"{digest}_{safe}"
        if dest.is_file() and dest.stat().st_size > 0:
            return dest
        remote_path = path
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = urljoin(self.base_url + "/", f"attachments/{quote(remote_path, safe='/')}")
        with httpx.Client(timeout=max(self.timeout, 60.0), follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        return dest

    def fetch_sample_submission(self) -> dict[str, Any]:
        if self._sample is not None:
            return self._sample
        local_sample = None
        if self.bundle:
            path = self.bundle / "sample_submission.json"
            if path.is_file():
                local_sample = json.loads(path.read_text(encoding="utf-8"))
        if local_sample is None:
            fallback = data_dir() / "sample_submission.json"
            if fallback.is_file():
                local_sample = json.loads(fallback.read_text(encoding="utf-8"))
        if isinstance(local_sample, dict) and local_sample:
            self._sample = local_sample
            return local_sample
        if not self.inbox_reachable():
            raise InboxError("sample_submission not found")
        resp = self._get("sample_submission")
        data = resp.json()
        if not isinstance(data, dict):
            raise InboxError("sample_submission is not an object")
        self._sample = data
        return data

    def sample_email_ids(self) -> list[str] | None:
        try:
            sample = self.fetch_sample_submission()
        except Exception:
            return None
        if not sample:
            return None
        # {email_id: {...}} or {predictions: {email_id: {...}}}
        if all(isinstance(v, dict) for v in sample.values()):
            keys = set(sample)
            if "predictions" in keys and isinstance(sample["predictions"], dict):
                return [str(k) for k in sample["predictions"]]
            if not keys & {"schema_version", "emails"}:
                return [str(k) for k in sample]
        if isinstance(sample.get("predictions"), dict):
            return [str(k) for k in sample["predictions"]]
        if isinstance(sample.get("emails"), dict):
            return [str(k) for k in sample["emails"]]
        return None

    def required_email_ids(self, *, source: str = "auto") -> list[str]:
        if source == "local":
            return self.list_email_ids(source="local")
        try:
            sample_ids = self.sample_email_ids()
        except Exception:
            sample_ids = None
        if sample_ids:
            return sample_ids
        if source == "official":
            return self._list_official()
        return self.list_email_ids(source=source)

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        from harbormaster.report.official_score import organizer_payload, persist_scoreboard

        body = organizer_payload(payload) if payload and isinstance(next(iter(payload.values()), None), dict) else payload
        resp = self._post("submit", body)
        data = resp.json()
        out = data if isinstance(data, dict) else {"result": data}
        try:
            persist_scoreboard(out, source=self.base_url or "submit")
        except Exception:
            pass
        return out

    def catalog(self, *, source: str = "official") -> list[dict[str, Any]]:
        """Subjects and attachment counts without running the court."""
        items: list[dict[str, Any]] = []
        for email_id in self.list_email_ids(source=source):
            items.append(self._catalog_item(email_id))
        return items

    def _catalog_item(self, email_id: str) -> dict[str, Any]:
        try:
            from harbormaster.ledger.store import LedgerStore

            cloud = LedgerStore().get_inbox_email(email_id)
        except Exception:
            cloud = None
        if cloud:
            return {
                "email_id": email_id,
                "subject": cloud.get("subject") or email_id,
                "from_addr": cloud.get("from_addr") or "",
                "attachments": int(cloud.get("attachment_count") or len(cloud.get("attachments") or [])),
                "source": "supabase",
            }
        folders: list[tuple[Path, str]] = []
        if self.official_inbox:
            folders.append((self.official_inbox, "official"))
        folders.append((self.inbox, "local"))
        for folder, source in folders:
            json_path = folder / f"{email_id}.json"
            if not json_path.is_file():
                continue
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}
            atts = _as_list(data.get("attachments") or data.get("attachment_paths") or data.get("files"))
            return {
                "email_id": email_id,
                "subject": _as_str(data.get("subject")) or email_id,
                "from_addr": _as_str(data.get("from_addr") or data.get("from") or data.get("sender")),
                "attachments": len(atts),
                "source": source,
            }
        return {
            "email_id": email_id,
            "subject": email_id,
            "from_addr": "",
            "attachments": 0,
            "source": "unknown",
        }

    def health(self) -> dict[str, Any]:
        official = self._list_official()
        local_demo = [i for i in self._list_folder(self.inbox) if is_demo_email_id(i)]
        info: dict[str, Any] = {
            "url": self.base_url,
            "ok": False,
            "email_count": 0,
            "source": "none",
            "bundle": str(self.bundle) if self.bundle else None,
            "official_count": len(official),
            "demo_count": len(local_demo),
        }
        try:
            cloud_ids = self._cloud_ids()
            if cloud_ids:
                info["ok"] = True
                info["email_count"] = len(cloud_ids)
                info["source"] = "supabase"
                info["official_count"] = len(cloud_ids)
                return info
            if self.inbox_reachable():
                ids = self.list_email_ids(source="remote")
                info["ok"] = True
                info["email_count"] = len(ids)
                info["source"] = "remote"
                return info
        except Exception as exc:  # noqa: BLE001
            info["error"] = str(exc)
        if official:
            info["ok"] = True
            info["email_count"] = len(official)
            info["source"] = "supabase" if self._cloud_ids() else "bundle"
            return info
        if local_demo:
            info["ok"] = True
            info["email_count"] = len(local_demo)
            info["source"] = "demo"
        return info
