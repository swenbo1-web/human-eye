"""Compare delivered saved-version previews with independent final-render pixels."""

import hashlib
import json
from pathlib import Path
import time

from PIL import Image

HERE = Path(__file__).resolve().parent


def identity(path):
    raw = path.read_bytes()
    return dict(path=path.relative_to(HERE).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    started, cpu = time.perf_counter(), time.process_time()
    pairs = []
    for route in ("facts", "native"):
        name = "v2_matched_" + route
        for view in ("whole_front", "forearm_front", "forearm_side", "forearm_45"):
            preview = HERE / "private/sessions" / name / "previews/v1/images" / (view + ".png")
            final = HERE / "private/results" / name / "after_views" / (view + ".png")
            with Image.open(preview) as first, Image.open(final) as second:
                initial_pixels, final_pixels = first.convert("RGBA"), second.convert("RGBA")
                matches = initial_pixels.size == final_pixels.size and initial_pixels.tobytes() == final_pixels.tobytes()
            pairs.append(dict(session=name, view=view, preview=identity(preview), final=identity(final), RGBA_equal=matches))
    record = dict(status="pass" if all(row["RGBA_equal"] for row in pairs) else "fail",
        pairs=pairs, passed=sum(row["RGBA_equal"] for row in pairs), total=len(pairs),
        source=identity(Path(__file__).resolve()), wall_s=time.perf_counter() - started,
        CPU_s=time.process_time() - cpu, Pro_calls=0, Blender_calls=0,
        interpretation="Actual preview PNGs match the separately rendered last saved models. Metadata-related PNG file hashes may differ.")
    (HERE / "PREVIEW_PIXEL_VERIFICATION.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({key: record[key] for key in ("status", "passed", "total", "wall_s", "CPU_s")}))
    if record["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
