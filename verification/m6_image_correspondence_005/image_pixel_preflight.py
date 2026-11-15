"""Compare shared PNG decoding with an independent Pillow process."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from image_inputs import image_inputs, read_png_rgb
from common import identity, write


def main():
    started, cpu = time.perf_counter(), time.process_time()
    rows = image_inputs(HERE / "private/consumer_cases/repair")
    output = HERE / "private/image_pixel_preflight" / uuid.uuid4().hex[:10]
    output.mkdir(parents=True)
    python = Path("C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe")
    program = """import hashlib,json,sys
from PIL import Image
rows=[]
for path in sys.argv[1:]:
    with Image.open(path) as image:
        image.load()
        rgb=image.convert('RGB')
        pixels=rgb.tobytes()
        rows.append(dict(path=path,size=list(rgb.size),RGB_bytes=len(pixels),RGB_sha256=hashlib.sha256(pixels).hexdigest()))
print(json.dumps(rows))
"""
    (output / "PILLOW_PROGRAM.py").write_text(program, encoding="utf8", newline="\n")
    command = [str(python), "-I", "-B", "-X", "utf8", "-c", program, *[row["path"] for row in rows]]
    begin_pillow = time.perf_counter()
    result = subprocess.run(command, capture_output=True, timeout=45,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    pillow_wall = time.perf_counter() - begin_pillow
    (output / "PILLOW_STDOUT.bin").write_bytes(result.stdout)
    (output / "PILLOW_STDERR.bin").write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError("Pillow_decoder_exit_" + str(result.returncode))
    independent = json.loads(result.stdout)
    checks, comparisons = {}, []
    for row, pillow in zip(rows, independent):
        raw = Path(row["path"]).read_bytes()
        pixels = read_png_rgb(raw)
        digest = hashlib.sha256(pixels.tobytes()).hexdigest()
        matches = pillow["size"] == [pixels.shape[1], pixels.shape[0]] and pillow["RGB_sha256"] == digest and pillow["RGB_bytes"] == pixels.nbytes
        checks[row["role"] + "_all_RGB_pixels_equal_Pillow"] = matches
        comparisons.append(dict(role=row["role"], PNG=identity(row["path"]), decoded_RGB_bytes=pixels.nbytes,
            decoded_RGB_sha256=digest, Pillow=pillow, RGB_equal=matches))
    altered = bytearray(Path(rows[0]["path"]).read_bytes())
    altered[29] ^= 1
    try:
        read_png_rgb(bytes(altered))
        checks["bad_PNG_CRC_rejected"] = False
    except ValueError:
        checks["bad_PNG_CRC_rejected"] = True
    checks["eight_roles_compared"] = len(comparisons) == len(independent) == 8
    record = dict(status="pass" if all(checks.values()) else "fail", checks=checks,
        comparisons=comparisons, shared_PNG_bytes=sum(row["bytes"] for row in rows),
        decoded_RGB_bytes=sum(row["decoded_RGB_bytes"] for row in comparisons),
        independent_Pillow_executable=identity(python), Pillow_wall_s=pillow_wall,
        wall_s=time.perf_counter() - started, parent_CPU_s=time.process_time() - cpu,
        actual_Pro_calls=0, actual_Blender_calls=0, evidence_directory=str(output.relative_to(HERE)))
    write(output / "RESULT.json", record)
    write("IMAGE_PIXEL_PREFLIGHT.json", record)
    print(json.dumps(dict(status=record["status"], checks=len(checks), wall_s=record["wall_s"], decoded_RGB_bytes=record["decoded_RGB_bytes"])))
    if record["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
