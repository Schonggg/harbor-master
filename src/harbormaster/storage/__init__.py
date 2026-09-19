"""Object storage: local disk by default, S3-compatible when S3_BUCKET is set."""

from harbormaster.storage.base import ObjectRef, ObjectStore
from harbormaster.storage.factory import get_object_store

__all__ = ["ObjectRef", "ObjectStore", "get_object_store"]
