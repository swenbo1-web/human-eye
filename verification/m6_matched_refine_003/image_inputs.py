"""Exact PNG inputs shared by CLI attachments and MCP image results."""

import base64
import hashlib
import json
from pathlib import Path
import struct


def image_inputs(case):
    case = Path(case).resolve()
    task = json.loads((case / "task.json").read_bytes())
    rows = []
    for index, item in enumerate(task["images"]):
        path = Path(item["path"])
        path = (path if path.is_absolute() else case / path).resolve()
        if not path.is_relative_to(case / "images") or path.suffix.lower() != ".png":
            raise ValueError("consumer_PNG_must_belong_to_current_case_images")
        raw = path.read_bytes()
        if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
            raise ValueError("image_input_requires_valid_PNG_header")
        width, height = struct.unpack(">II", raw[16:24])
        row = dict(index=index + 1, role=item["role"], path=str(path), bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(), width=width, height=height, mimeType="image/png")
        for key in ("sha256", "bytes", "width", "height"):
            if key in item and item[key] != row[key]:
                raise ValueError("frozen_image_identity_mismatch_" + key)
        rows.append(row)
    if not rows or len(rows) != task.get("image_count", len(task["images"])):
        raise ValueError("actual_reference_and_model_images_required")
    return rows


def image_content(rows):
    content = [dict(type="text", text=json.dumps(dict(images=rows), ensure_ascii=True))]
    for row in rows:
        raw = Path(row["path"]).read_bytes()
        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("image_changed_before_MCP_delivery")
        content.append(dict(type="image", data=base64.b64encode(raw).decode("ascii"), mimeType=row["mimeType"]))
    return content
