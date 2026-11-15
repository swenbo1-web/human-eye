"""Exact PNG inputs shared by CLI attachments and MCP image results."""

import base64
import hashlib
import json
from pathlib import Path
import struct
import zlib


def read_png_rgb(raw):
    """Decode the bound 8-bit RGB/RGBA PNG bytes without reading other files."""
    import numpy as np
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("image_pixels_require_PNG")
    offset, blocks, header = 8, [], None
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise ValueError("truncated_PNG_chunk")
        size = struct.unpack(">I", raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        data = raw[offset + 8:offset + 8 + size]
        crc_bytes = raw[offset + 8 + size:offset + 12 + size]
        if len(data) != size or len(crc_bytes) != 4 or zlib.crc32(kind + data) & 0xffffffff != struct.unpack(">I", crc_bytes)[0]:
            raise ValueError("PNG_chunk_CRC_or_length_mismatch")
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", data)
        if kind == b"IDAT":
            blocks.append(data)
        offset += size + 12
        if kind == b"IEND":
            break
    if header is None or offset != len(raw):
        raise ValueError("PNG_header_or_ending_invalid")
    width, height, bits, color, compression, filtering, interlace = header
    if bits != 8 or color not in (2, 6) or compression or filtering or interlace:
        raise ValueError("PNG_requires_noninterlaced_8bit_RGB_or_RGBA")
    channels = 4 if color == 6 else 3
    stride = width * channels
    stream = zlib.decompress(b"".join(blocks))
    if len(stream) != height * (stride + 1):
        raise ValueError("PNG_scanline_size_mismatch")
    image = np.zeros((height, stride), dtype=np.uint8)
    for row_index in range(height):
        start = row_index * (stride + 1)
        mode = stream[start]
        row = np.frombuffer(stream[start + 1:start + 1 + stride], dtype=np.uint8).astype(np.int32)
        previous = image[row_index - 1].astype(np.int32) if row_index else np.zeros(stride, dtype=np.int32)
        if mode == 1:
            for channel in range(channels):
                row[channel::channels] = np.cumsum(row[channel::channels]) % 256
        elif mode == 2:
            row = (row + previous) % 256
        elif mode in (3, 4):
            for column in range(stride):
                left = int(row[column - channels]) if column >= channels else 0
                up = int(previous[column])
                upper_left = int(previous[column - channels]) if column >= channels else 0
                predictor = (left + up) // 2
                if mode == 4:
                    estimate = left + up - upper_left
                    distances = (abs(estimate - left), abs(estimate - up), abs(estimate - upper_left))
                    predictor = (left, up, upper_left)[int(np.argmin(distances))]
                row[column] = (int(row[column]) + predictor) % 256
        elif mode != 0:
            raise ValueError("PNG_filter_unavailable")
        image[row_index] = row
    return image.reshape(height, width, channels)[:, :, :3].copy()


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
        if "camera" in item:
            row["camera"] = item["camera"]
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
