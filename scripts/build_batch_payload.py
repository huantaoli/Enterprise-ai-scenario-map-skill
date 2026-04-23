#!/usr/bin/env python3
"""
Build a deterministic batch payload for the Bitable batch-build API.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def load_table_list(path: Path) -> List[Dict[str, Any]]:
    """Load the confirmed intermediate table list from disk."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("input must be a JSON array")

    return data


def validate_table_list(items: List[Dict[str, Any]]) -> None:
    """Validate the confirmed intermediate table list."""
    if not items:
        raise ValueError("input table list must not be empty")

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"item {index} must be an object")

        table_name = str(item.get("table_name", "")).strip()
        user_requirement = str(item.get("user_requirement", "")).strip()

        if not table_name:
            raise ValueError(f"item {index} is missing a non-empty table_name")
        if not user_requirement:
            raise ValueError(f"item {index} is missing a non-empty user_requirement")


def generate_batch_id() -> str:
    """Generate a unique client batch id."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"batch-{timestamp}-{suffix}"


def generate_item_id(index: int) -> str:
    """Generate a unique item id inside a batch."""
    suffix = uuid.uuid4().hex[:6]
    return f"req-{index:03d}-{suffix}"


def build_defaults(language: str, with_generate_flowchart: bool, prompt_variant: str) -> Dict[str, Any]:
    """Build the defaults section for the API payload."""
    return {
        "language": language,
        "with_generate_flowchart": with_generate_flowchart,
        "extra": {
            "prompt_variant": prompt_variant,
        },
    }


def build_payload(
    items: List[Dict[str, Any]],
    language: str,
    with_generate_flowchart: bool,
    prompt_variant: str,
    max_concurrency: int,
    continue_on_error: bool,
) -> Dict[str, Any]:
    """Build the final batch payload."""
    payload_items: List[Dict[str, Any]] = []
    seen_ids = set()

    for index, item in enumerate(items, start=1):
        client_item_id = generate_item_id(index)
        if client_item_id in seen_ids:
            raise ValueError("generated duplicate client_item_id")
        seen_ids.add(client_item_id)

        payload_item: Dict[str, Any] = {
            "client_item_id": client_item_id,
            "user_requirement": item["user_requirement"].strip(),
        }

        if "language" in item and str(item["language"]).strip():
            payload_item["language"] = str(item["language"]).strip()
        if "with_generate_flowchart" in item:
            payload_item["with_generate_flowchart"] = bool(item["with_generate_flowchart"])
        if "extra" in item and isinstance(item["extra"], dict) and item["extra"]:
            payload_item["extra"] = item["extra"]

        payload_items.append(payload_item)

    return {
        "client_batch_id": generate_batch_id(),
        "items": payload_items,
        "defaults": build_defaults(language, with_generate_flowchart, prompt_variant),
        "max_concurrency": max_concurrency,
        "continue_on_error": continue_on_error,
    }


def write_payload(payload: Dict[str, Any], output_path: Path) -> None:
    """Write the payload JSON to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Build a batch payload for the Bitable batch-build API")
    parser.add_argument("--input", required=True, help="path to the confirmed table-list JSON file")
    parser.add_argument("--output", required=True, help="path to write the generated batch payload JSON")
    parser.add_argument("--language", default="zh", help="default output language")
    parser.add_argument(
        "--with-generate-flowchart",
        action="store_true",
        help="request flowchart generation by default",
    )
    parser.add_argument(
        "--prompt-variant",
        default="current",
        help="prompt variant for defaults.extra.prompt_variant",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=3,
        help="maximum number of items to run concurrently",
    )
    parser.add_argument(
        "--continue-on-error",
        dest="continue_on_error",
        action="store_true",
        default=True,
        help="continue processing remaining items if one item fails",
    )
    parser.add_argument(
        "--stop-on-error",
        dest="continue_on_error",
        action="store_false",
        help="stop processing remaining items if one item fails",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()

    try:
        input_path = Path(args.input).resolve()
        output_path = Path(args.output).resolve()

        items = load_table_list(input_path)
        validate_table_list(items)

        payload = build_payload(
            items=items,
            language=args.language,
            with_generate_flowchart=args.with_generate_flowchart,
            prompt_variant=args.prompt_variant,
            max_concurrency=args.max_concurrency,
            continue_on_error=args.continue_on_error,
        )
        write_payload(payload, output_path)

        result = {
            "type": "batch_payload_built",
            "payload_path": str(output_path),
            "client_batch_id": payload["client_batch_id"],
            "item_count": len(payload["items"]),
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0

    except Exception as exc:  # pragma: no cover - CLI safety path
        print(json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
