#!/usr/bin/env python3
"""
Lightweight runtime state helpers for the skill 3.0 MVP.

This module stores only the minimum local state needed to recover from
post-acceptance SSE interruptions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


STATE_DIR_NAME = ".runtime"
STATE_FILE_NAME = "skill_3_0_runtime_state.json"


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_repo_root() -> Path:
    """Resolve the repository root from this script location."""
    return Path(__file__).resolve().parent.parent


def get_state_path() -> Path:
    """Return the path to the local runtime-state file."""
    return get_repo_root() / STATE_DIR_NAME / STATE_FILE_NAME


def load_state() -> Dict[str, Any]:
    """Load the current runtime state if it exists."""
    state_path = get_state_path()
    if not state_path.exists():
        return {}

    with state_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_state(state: Dict[str, Any]) -> Path:
    """Persist the runtime state and return the state-file path."""
    state_path = get_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    payload = dict(state)
    payload["updated_at"] = utc_now_iso()

    with state_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")

    return state_path


def merge_state(**fields: Any) -> Dict[str, Any]:
    """Merge the provided fields into the stored runtime state."""
    state = load_state()
    for key, value in fields.items():
        if value is None:
            state.pop(key, None)
        else:
            state[key] = value
    save_state(state)
    return state


def update_request_id(request_id: str) -> Dict[str, Any]:
    """Persist the request id after a batch is accepted."""
    return merge_state(request_id=request_id)


def clear_state() -> None:
    """Remove the runtime-state file if it exists."""
    state_path = get_state_path()
    if state_path.exists():
        state_path.unlink()


def set_initial_state(
    client_batch_id: str,
    payload_path: Optional[str] = None,
    api_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Store the initial runtime state before the batch is submitted."""
    return merge_state(
        client_batch_id=client_batch_id,
        payload_path=payload_path,
        api_base_url=api_base_url,
        request_id=None,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inspect or clear skill 3.0 runtime state")
    parser.add_argument("--clear", action="store_true", help="clear the current runtime state")
    args = parser.parse_args()

    if args.clear:
        clear_state()
        print(json.dumps({"type": "runtime_state_cleared"}, ensure_ascii=False))
    else:
        print(json.dumps(load_state(), ensure_ascii=False, indent=2))
