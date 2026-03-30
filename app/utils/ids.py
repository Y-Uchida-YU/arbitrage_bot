from __future__ import annotations

import uuid


def new_run_id() -> str:
    return uuid.uuid4().hex


def new_idempotency_key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"