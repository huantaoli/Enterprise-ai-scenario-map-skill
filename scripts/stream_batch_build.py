#!/usr/bin/env python3
"""
Submit a Bitable batch-build request and stream SSE progress.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from runtime_state import clear_state, set_initial_state, update_request_id


def emit(event_type: str, **fields: Any) -> None:
    """Emit a stable JSON line for the caller to parse."""
    payload = {"type": event_type}
    payload.update(fields)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def load_payload(path: Path) -> Dict[str, Any]:
    """Load the batch payload from disk."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    if not data.get("client_batch_id"):
        raise ValueError("payload is missing client_batch_id")
    if not isinstance(data.get("items"), list) or not data["items"]:
        raise ValueError("payload must contain a non-empty items list")
    return data


def submit_batch(payload: Dict[str, Any], api_base_url: str):
    """Submit the batch payload and return the HTTP response object."""
    url = urllib.parse.urljoin(api_base_url.rstrip("/") + "/", "api/bitable/build/batch")
    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=1800)


def iter_sse_messages(lines: Iterable[str]) -> Iterator[Dict[str, str]]:
    """Parse SSE messages from the response line iterator."""
    event_name: Optional[str] = None
    data_lines: List[str] = []

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")

        if not line:
            if data_lines:
                yield {
                    "event": event_name or "",
                    "data": "\n".join(data_lines),
                }
            event_name = None
            data_lines = []
            continue

        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())

    if data_lines:
        yield {
            "event": event_name or "",
            "data": "\n".join(data_lines),
        }


def parse_event(message: Dict[str, str]) -> Dict[str, Any]:
    """Decode the JSON payload in an SSE message."""
    try:
        event = json.loads(message["data"])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in SSE data: {exc}") from exc

    if not isinstance(event, dict):
        raise ValueError("SSE data must decode to a JSON object")
    if "event" not in event:
        event["event"] = message.get("event", "")
    return event


def query_batch_status(request_id: str, api_base_url: str) -> Dict[str, Any]:
    """Query the batch status endpoint by request id."""
    path = f"api/bitable/build/batch/{urllib.parse.quote(request_id)}/status"
    url = urllib.parse.urljoin(api_base_url.rstrip("/") + "/", path)
    request = urllib.request.Request(url=url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("status endpoint returned a non-object JSON payload")
    return data


def handle_stream(payload: Dict[str, Any], payload_path: Path, api_base_url: str) -> Dict[str, Any]:
    """Submit the batch request, stream events, and return the final state."""
    client_batch_id = payload["client_batch_id"]
    set_initial_state(
        client_batch_id=client_batch_id,
        payload_path=str(payload_path),
        api_base_url=api_base_url,
    )

    request_id: Optional[str] = None
    final_event: Optional[Dict[str, Any]] = None

    try:
        with submit_batch(payload, api_base_url) as response:
            if response.status >= 400:
                raise RuntimeError(f"batch submission failed with HTTP {response.status}")

            for message in iter_sse_messages(
                line.decode("utf-8", errors="replace") for line in response
            ):
                event = parse_event(message)
                event_name = str(event.get("event", "")).strip()

                if event_name == "batch_accepted":
                    request_id = str(event.get("request_id", "")).strip() or None
                    if request_id:
                        update_request_id(request_id)
                    emit("batch_accepted", event=event)
                elif event_name == "job_progress":
                    emit("job_progress", event=event)
                elif event_name == "job_complete":
                    emit("job_complete", event=event)
                elif event_name == "batch_complete":
                    final_event = event
                    emit("batch_complete", event=event)
                    break
                else:
                    emit("unknown_event", event=event)

    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        if request_id:
            status = query_batch_status(request_id, api_base_url)
            emit("status_lookup", event=status)
            return status
        raise RuntimeError(f"stream connection failed before request recovery: {exc}") from exc
    except Exception:
        if request_id:
            status = query_batch_status(request_id, api_base_url)
            emit("status_lookup", event=status)
            return status
        raise

    if final_event is not None:
        return final_event

    if request_id:
        status = query_batch_status(request_id, api_base_url)
        emit("status_lookup", event=status)
        return status

    raise RuntimeError("stream ended before batch_accepted; no request_id available for recovery")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Submit a Bitable batch-build request and stream progress")
    parser.add_argument("--payload", required=True, help="path to the batch payload JSON file")
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:1128",
        help="base URL for the batch-build API",
    )
    parser.add_argument(
        "--keep-state",
        action="store_true",
        help="keep the local runtime-state file after completion",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()

    try:
        payload_path = Path(args.payload).resolve()
        payload = load_payload(payload_path)
        final_result = handle_stream(payload, payload_path, args.api_base_url)
        emit("final_summary", event=final_result)
        return 0
    except Exception as exc:  # pragma: no cover - CLI safety path
        emit("error", message=str(exc))
        return 1
    finally:
        if not args.keep_state:
            clear_state()


if __name__ == "__main__":
    sys.exit(main())
