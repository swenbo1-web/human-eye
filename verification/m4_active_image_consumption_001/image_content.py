"""Build MCP image content from a registered, unchanged PNG.

Importing this module performs no file read, image generation, or model call.
The returned audit receipt is private to the experiment controller.
"""

import base64
import hashlib
import json
from pathlib import Path
import struct
import time
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ImageContentError(ValueError):
    def __init__(self, reason, receipt):
        super().__init__(reason)
        self.receipt = receipt


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def deadline(deadline_ns):
    if type(deadline_ns) is not int or time.perf_counter_ns() >= deadline_ns:
        raise TimeoutError("original_route_deadline")


def validate_png(raw, expected_width, expected_height):
    """Validate the complete PNG stream and decode its scanline structure."""
    if raw[:8] != PNG_SIGNATURE:
        raise ValueError("image_png_signature")
    offset = 8
    chunks = []
    compressed = bytearray()
    dimensions = None
    ended = False
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise ValueError("image_png_truncated_chunk")
        length = struct.unpack(">I", raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(raw):
            raise ValueError("image_png_chunk_length")
        payload = raw[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", raw[offset + 8 + length:end])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError("image_png_crc")
        if not chunks and kind != b"IHDR":
            raise ValueError("image_png_first_header")
        if kind == b"IHDR":
            if chunks or length != 13:
                raise ValueError("image_png_header")
            width, height, bit_depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload)
            if (width, height) != (expected_width, expected_height):
                raise ValueError("image_png_dimensions")
            if bit_depth != 8 or color not in (2, 6) or (compression, filtering, interlace) != (0, 0, 0):
                raise ValueError("image_png_registered_format")
            dimensions = (width, height, 3 if color == 2 else 4)
        elif kind == b"IDAT":
            if b"IEND" in chunks:
                raise ValueError("image_png_data_after_end")
            compressed.extend(payload)
        elif kind == b"IEND":
            if length or end != len(raw):
                raise ValueError("image_png_end")
            ended = True
        elif kind[:1].isupper():
            raise ValueError("image_png_unregistered_critical_chunk")
        chunks.append(kind)
        offset = end
    if not ended or b"IDAT" not in chunks or dimensions is None:
        raise ValueError("image_png_incomplete")
    width, height, channels = dimensions
    expected_size = height * (1 + width * channels)
    decoder = zlib.decompressobj()
    scanlines = decoder.decompress(bytes(compressed), expected_size + 1)
    if (len(scanlines) != expected_size or not decoder.eof or decoder.unused_data or
            decoder.unconsumed_tail):
        raise ValueError("image_png_decoded_length")
    stride = width * channels + 1
    if any(scanlines[row * stride] > 4 for row in range(height)):
        raise ValueError("image_png_scanline_filter")
    return {"width": width, "height": height, "channels": channels,
            "decoded_scanline_bytes": len(scanlines), "chunk_count": len(chunks)}


def image_content(specification, input_directory, deadline_ns):
    """Return one standard ImageContent and a private measured receipt.

    Both experiment routes call this function. It reads and base64-encodes the
    original PNG bytes without resizing or reconstructing the image.
    """
    receipt = {"ref": specification.get("ref"), "started_ns": time.perf_counter_ns(),
               "constructed": False, "PNG_bytes_read": 0, "base64_chars": 0, "stages": {}}
    try:
        deadline(deadline_ns)
        if specification["mimeType"] != "image/png":
            raise ValueError("image_mime_type")
        if (specification["width"], specification["height"]) != (512, 512):
            raise ValueError("image_registered_512_dimensions")
        directory = Path(input_directory).resolve()
        path = (directory / specification["file"]).resolve()
        if path.parent != directory or path.suffix.lower() != ".png":
            raise ValueError("image_registered_input_path")
        mark = time.perf_counter_ns()
        raw = path.read_bytes()
        closed = time.perf_counter_ns()
        receipt["stages"]["read"] = {"started_ns": mark, "closed_ns": closed, "elapsed_ns": closed - mark}
        receipt["PNG_bytes_read"] = len(raw)
        receipt["PNG_sha256"] = hashlib.sha256(raw).hexdigest()
        if len(raw) != specification["PNG_bytes"] or receipt["PNG_sha256"] != specification["sha256"]:
            raise ValueError("image_registered_bytes_changed")
        deadline(deadline_ns)
        mark = time.perf_counter_ns()
        receipt["decoded"] = validate_png(raw, specification["width"], specification["height"])
        closed = time.perf_counter_ns()
        receipt["stages"]["validate_decode"] = {
            "started_ns": mark, "closed_ns": closed, "elapsed_ns": closed - mark}
        mark = time.perf_counter_ns()
        payload = base64.b64encode(raw).decode("ascii")
        if base64.b64decode(payload, validate=True) != raw:
            raise ValueError("image_base64_roundtrip")
        block = {"type": "image", "data": payload, "mimeType": "image/png"}
        receipt["base64_chars"] = len(payload)
        receipt["image_block_JSON_bytes"] = len(encoded(block))
        closed = time.perf_counter_ns()
        receipt["stages"]["encode"] = {"started_ns": mark, "closed_ns": closed, "elapsed_ns": closed - mark}
        deadline(deadline_ns)
        receipt["constructed"] = True
        receipt["closed_ns"] = time.perf_counter_ns()
        receipt["elapsed_ns"] = receipt["closed_ns"] - receipt["started_ns"]
        return block, receipt
    except BaseException as error:
        receipt["closed_ns"] = time.perf_counter_ns()
        receipt["elapsed_ns"] = receipt["closed_ns"] - receipt["started_ns"]
        receipt["error"] = {"type": type(error).__name__, "reason": str(error)}
        raise ImageContentError(str(error), receipt) from error
