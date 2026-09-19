from __future__ import annotations

import os
from functools import lru_cache

from harbormaster.config import get_settings
from harbormaster.storage.base import ObjectStore
from harbormaster.storage.local import LocalObjectStore
from harbormaster.storage.s3 import S3ObjectStore


@lru_cache(maxsize=1)
def get_object_store() -> ObjectStore:
    settings = get_settings()
    bucket = (os.getenv("S3_BUCKET") or settings.s3_bucket or "").strip()
    if not bucket:
        return LocalObjectStore()
    return S3ObjectStore(
        bucket=bucket,
        access_key=os.getenv("S3_ACCESS_KEY") or settings.s3_access_key,
        secret_key=os.getenv("S3_SECRET_KEY") or settings.s3_secret_key,
        region=os.getenv("S3_REGION") or settings.s3_region,
        endpoint=os.getenv("S3_ENDPOINT") or settings.s3_endpoint,
        prefix=settings.object_prefix,
        force_path_style=settings.s3_force_path_style,
    )


def reset_object_store() -> None:
    get_object_store.cache_clear()
