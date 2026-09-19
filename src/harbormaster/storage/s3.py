"""Minimal S3-compatible client (AWS / R2 / MinIO) using httpx + SigV4."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from urllib.parse import quote

import httpx

from harbormaster.storage.base import ObjectRef

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date: str, region: str, service: str = "s3") -> bytes:
    k_date = _hmac(("AWS4" + secret).encode("utf-8"), date)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def canonical_uri(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return quote(path, safe="/-_.~")


class S3ObjectStore:
    backend = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        endpoint: str = "",
        prefix: str = "harbormaster/",
        force_path_style: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self.bucket = bucket.strip()
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region or "us-east-1"
        self.endpoint = endpoint.rstrip("/")
        self.prefix = prefix if prefix.endswith("/") else prefix + "/"
        self.force_path_style = force_path_style or bool(self.endpoint)
        self.timeout = timeout

    def _full_key(self, key: str) -> str:
        clean = key.replace("\\", "/").lstrip("/")
        return f"{self.prefix}{clean}"

    def _host_and_url(self, key: str) -> tuple[str, str, str]:
        full = self._full_key(key)
        if self.force_path_style:
            base = self.endpoint or f"https://s3.{self.region}.amazonaws.com"
            host = base.replace("https://", "").replace("http://", "").split("/")[0]
            url = f"{base}/{self.bucket}/{full}"
            uri = f"/{self.bucket}/{full}"
            return host, url, uri
        host = f"{self.bucket}.s3.{self.region}.amazonaws.com"
        url = f"https://{host}/{full}"
        return host, url, f"/{full}"

    def _headers(self, method: str, key: str, payload: bytes) -> tuple[str, dict[str, str]]:
        host, url, uri = self._host_and_url(key)
        now = dt.datetime.now(dt.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(payload).hexdigest()
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical = "\n".join(
            [
                method,
                canonical_uri(uri),
                "",
                f"host:{host}",
                f"x-amz-content-sha256:{payload_hash}",
                f"x-amz-date:{amz_date}",
                "",
                signed_headers,
                payload_hash,
            ]
        )
        scope = f"{datestamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            ]
        )
        signature = hmac.new(
            _signing_key(self.secret_key, datestamp, self.region),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        auth = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers = {
            "Authorization": auth,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
            "Host": host,
        }
        return url, headers

    def _request(self, method: str, key: str, payload: bytes = b"") -> httpx.Response:
        url, headers = self._headers(method, key, payload)
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            return client.request(method, url, headers=headers, content=payload or None)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> ObjectRef:
        resp = self._request("PUT", key, data)
        if resp.status_code not in {200, 201, 204}:
            raise RuntimeError(f"S3 PUT failed ({resp.status_code}): {resp.text[:240]}")
        _host, url, _uri = self._host_and_url(key)
        return ObjectRef(
            key=key,
            backend=self.backend,
            bytes=len(data),
            content_type=content_type,
            uri=url,
        )

    def get(self, key: str) -> bytes:
        resp = self._request("GET", key, b"")
        if resp.status_code == 404:
            raise FileNotFoundError(key)
        if resp.status_code != 200:
            raise RuntimeError(f"S3 GET failed ({resp.status_code}): {resp.text[:240]}")
        return resp.content

    def exists(self, key: str) -> bool:
        resp = self._request("HEAD", key, b"")
        return resp.status_code == 200

    def health(self) -> dict:
        probe_key = ".health"
        try:
            self.put(probe_key, b"ok", "text/plain")
            ok = self.get(probe_key) == b"ok"
            return {
                "ok": ok,
                "backend": self.backend,
                "bucket": self.bucket,
                "prefix": self.prefix,
                "endpoint": self.endpoint or f"s3.{self.region}.amazonaws.com",
                "error": "" if ok else "read-after-write mismatch",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "backend": self.backend,
                "bucket": self.bucket,
                "prefix": self.prefix,
                "endpoint": self.endpoint or f"s3.{self.region}.amazonaws.com",
                "error": str(exc)[:200],
            }
