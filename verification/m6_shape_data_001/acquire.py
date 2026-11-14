"""Acquire the four authorized sources without saving any source file."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE_ROOT = Path("D:/codex data/2026-10-02/fps-blender-models")
BLENDER = Path("D:/Tools/blender5.2/blender.exe")


def record(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def process_cpu_seconds(process):
    times = [wintypes.FILETIME() for _ in range(4)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    if not kernel.GetProcessTimes(int(process._handle), *[ctypes.byref(value) for value in times]):
        return {"status": "unavailable", "winerror": ctypes.get_last_error()}
    ticks = sum((value.dwHighDateTime << 32) + value.dwLowDateTime for value in times[2:])
    return {"status": "measured", "cpu_s": ticks / 10_000_000, "scope": "full child process kernel plus user time"}


def main():
    private = HERE / "private"
    private.mkdir(exist_ok=True)
    manifest_path = HERE / "SOURCE_MANIFEST.json"
    if manifest_path.exists():
        raise RuntimeError("acquisition_already_recorded_inspect_before_retry")
    started, cpu_started = time.perf_counter(), time.process_time()
    manifest = {"cycle_id": "M6-SHAPE-DATA-001", "sources": [], "attempts": [], "new_Blender_processes": 0,
                "blender_binary": record(BLENDER), "collector": record(HERE / "collect_native.py")}
    environment = dict(os.environ)
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        environment[name] = "1"
    for name in ("Yanyite", "Richie", "Chipow", "Yunhex"):
        original = SOURCE_ROOT / name / "outputs" / f"{name}_Appearance.blend"
        source = {"name": name, "original": record(original)}
        source_dir = private / name
        source_dir.mkdir(exist_ok=True)
        if name == "Yanyite":
            reused = ROOT / "verification/m6_real_data_001/private/capture_02"
            source.update(raw=record(reused / "raw_selected.json"), native=record(reused / "native_inventory.json"),
                          acquisition="reuse frozen M6-REAL-DATA-001 capture_02", incremental_export_wall_s=0.)
        else:
            copied = source_dir / original.name
            shutil.copyfile(original, copied)
            assert record(copied)["sha256"] == source["original"]["sha256"]
            command = [str(BLENDER), "--factory-startup", "--disable-autoexec", "--background", "--threads", "1",
                       str(copied), "--python-exit-code", "23", "--python", str(HERE / "collect_native.py"),
                       "--", "--out", str(source_dir), "--original", str(original)]
            attempt = {"source": name, "command": command, "status": "running"}
            manifest["attempts"].append(attempt)
            write(manifest_path, manifest)
            before = time.perf_counter()
            with subprocess.Popen(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  creationflags=subprocess.CREATE_NO_WINDOW) as process:
                manifest["new_Blender_processes"] += 1
                try:
                    stdout, stderr = process.communicate(timeout=90)
                    attempt.update(returncode=process.returncode, status="exported" if process.returncode == 0 else "failed")
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                    attempt.update(returncode=process.returncode, status="timeout")
                attempt["process_cpu"] = process_cpu_seconds(process)
            attempt["full_process_wall_s"] = time.perf_counter() - before
            (HERE / f"{name}.stdout.log").write_bytes(stdout)
            (HERE / f"{name}.stderr.log").write_bytes(stderr)
            attempt["source_unchanged"] = record(original) == source["original"]
            attempt["copy_unchanged"] = record(copied)["sha256"] == source["original"]["sha256"]
            write(manifest_path, manifest)
            if attempt["status"] != "exported" or not attempt["source_unchanged"] or not attempt["copy_unchanged"]:
                raise RuntimeError("acquisition_failure_preserved_in_manifest")
            native = json.loads((source_dir / "native_inventory.json").read_bytes())
            assert native["autoexec_enabled"] is False
            source.update(raw=record(source_dir / "raw_selected.json"), native=record(source_dir / "native_inventory.json"),
                          evaluated=record(source_dir / "evaluated_selected.json"), isolated_copy=record(copied),
                          acquisition="factory isolated background process", incremental_export_wall_s=attempt["full_process_wall_s"])
        native = json.loads(Path(source["native"]["path"]).read_bytes())
        raw = json.loads(Path(source["raw"]["path"]).read_bytes())
        selected = next(row for row in native["objects"] if row["name"] == raw["object_name"])
        source["selected_object"] = selected
        source["raw_evaluated"] = native["exported_object"]
        source["scenes"] = native["scenes"]
        source["counts"] = {"vertices": len(raw["vertices_world"]), "triangles": len(raw["triangles"])}
        source["source_after"] = record(original)
        assert source["source_after"] == source["original"]
        manifest["sources"].append(source)
        write(manifest_path, manifest)
        print(json.dumps({"source": name, **source["counts"], "acquisition": source["acquisition"]}), flush=True)
    manifest.update(status="completed", controller_wall_s=time.perf_counter() - started,
                    controller_cpu_s=time.process_time() - cpu_started,
                    private_bytes=sum(path.stat().st_size for path in private.rglob("*") if path.is_file()),
                    source_saves=0, shared_GUI_calls=0, formal_performance=False)
    write(manifest_path, manifest)


if __name__ == "__main__":
    main()
