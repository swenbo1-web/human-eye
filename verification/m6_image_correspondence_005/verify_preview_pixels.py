"""Compare delivered saved-version previews with independent final-render pixels."""

import argparse
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2", "all"), default="all")
    selected_stage = parser.parse_args().stage
    pairs, missing = [], []
    for stage, route in (("v1", "native"), ("v1", "facts"), ("v2", "facts"), ("v2", "native")):
        if selected_stage != "all" and stage != selected_stage:
            continue
        name = stage + "_repair_" + route
        directory = HERE / "private/sessions" / name
        version = json.loads((directory / "session.json").read_bytes())["version"]
        for view in ("whole_front", "forearm_front", "forearm_side", "forearm_45"):
            preview = directory / "previews" / ("v" + str(version)) / "images" / (view + ".png")
            if version == 0:
                preview = HERE / "private/consumer_cases/repair/images" / ("current_" + view + ".png")
            if not preview.exists():
                missing.append(dict(session=name, view=view, version=version, reason="Final-version preview artifact absent"))
                continue
            final = HERE / "private/results" / name / "after_views" / (view + ".png")
            with Image.open(preview) as first, Image.open(final) as second:
                initial_pixels, final_pixels = first.convert("RGBA"), second.convert("RGBA")
                matches = initial_pixels.size == final_pixels.size and initial_pixels.tobytes() == final_pixels.tobytes()
            pairs.append(dict(session=name, view=view, preview=identity(preview), final=identity(final), RGBA_equal=matches))
    record = dict(stage=selected_stage, status="pass" if pairs and all(row["RGBA_equal"] for row in pairs) else "fail",
        missing_final_preview=missing,
        pairs=pairs, passed=sum(row["RGBA_equal"] for row in pairs), total=len(pairs),
        source=identity(Path(__file__).resolve()), wall_s=time.perf_counter() - started,
        CPU_s=time.process_time() - cpu, Pro_calls=0, Blender_calls=0,
        interpretation="Existing final preview PNGs or initial-current PNGs for unedited copies are compared with independent final renders. Missing final previews remain recorded.")
    (HERE / ("PREVIEW_PIXEL_VERIFICATION_" + selected_stage + ".json")).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({key: record[key] for key in ("status", "passed", "total", "wall_s", "CPU_s")}))
    if record["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
