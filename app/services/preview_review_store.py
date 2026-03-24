"""Ephemeral storage for preview AI review batches."""
from __future__ import annotations

import threading
import time
import uuid
from copy import deepcopy
from typing import Optional

PREVIEW_BATCH_TTL_SECONDS = 30 * 60


class PreviewReviewStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._batches: dict[str, dict] = {}

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [
            batch_id
            for batch_id, payload in self._batches.items()
            if payload.get("expires_at", 0) <= now
        ]
        for batch_id in expired:
            self._batches.pop(batch_id, None)

    def create_batch(self, questions: list[dict], stats: dict) -> uuid.UUID:
        batch_id = uuid.uuid4()
        now = time.time()
        payload = {
            "preview_batch_id": str(batch_id),
            "created_at": now,
            "expires_at": now + PREVIEW_BATCH_TTL_SECONDS,
            "questions": deepcopy(questions),
            "stats": deepcopy(stats),
            "pending": True,
            "completed": False,
            "failed": False,
            "error": None,
        }
        with self._lock:
            self._purge_expired()
            self._batches[str(batch_id)] = payload
        return batch_id

    def get_batch(self, batch_id: uuid.UUID | str) -> Optional[dict]:
        key = str(batch_id)
        with self._lock:
            self._purge_expired()
            payload = self._batches.get(key)
            return deepcopy(payload) if payload else None

    def update_batch(self, batch_id: uuid.UUID | str, **updates) -> Optional[dict]:
        key = str(batch_id)
        with self._lock:
            self._purge_expired()
            payload = self._batches.get(key)
            if not payload:
                return None
            payload.update(deepcopy(updates))
            payload["expires_at"] = time.time() + PREVIEW_BATCH_TTL_SECONDS
            return deepcopy(payload)


preview_review_store = PreviewReviewStore()
