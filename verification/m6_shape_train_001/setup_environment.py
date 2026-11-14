"""Download official CPU wheels, hash-lock them, install into a private venv."""
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from process_runner import run


def main():
    started = time.perf_counter()
    private = HERE / "private"
    private.mkdir(exist_ok=True)
    python = private / "venv/Scripts/python.exe"
    if python.exists():
        raise RuntimeError("venv_already_present_inspect_before_retry")
    records = []
    records.append(run([sys.executable, "-I", "-B", "-m", "venv", str(private / "venv")], "venv_create"))
    if records[-1]["returncode"]:
        raise RuntimeError("venv_creation_failed")
    wheels = private / "wheels"
    wheels.mkdir(exist_ok=True)
    records.append(run([str(python), "-m", "pip", "download", "--only-binary=:all:", "--progress-bar", "off", "--index-url",
                        "https://download.pytorch.org/whl/cpu", "--dest", str(wheels), "torch"], "torch_download"))
    if records[-1]["returncode"]:
        raise RuntimeError("official_torch_download_failed")
    records.append(run([str(python), "-m", "pip", "download", "--only-binary=:all:", "--progress-bar", "off", "--index-url",
                        "https://pypi.org/simple", "--dest", str(wheels), "numpy==2.3.5"], "numpy_download"))
    if records[-1]["returncode"]:
        raise RuntimeError("numpy_download_failed")
    wheel_records = []
    for wheel in sorted(wheels.glob("*.whl")):
        data = wheel.read_bytes()
        wheel_records.append({"filename": wheel.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    assert wheel_records
    requirements = []
    for wheel in wheel_records:
        parts = wheel["filename"].split("-")
        requirements.append(parts[0].replace("_", "-") + "==" + parts[1] + " --hash=sha256:" + wheel["sha256"])
    lock = HERE / "requirements.lock.txt"
    lock.write_text("\n".join(requirements) + "\n", encoding="utf-8", newline="\n")
    records.append(run([str(python), "-m", "pip", "install", "--no-index", "--find-links", str(wheels), "--require-hashes",
                        "-r", str(lock)], "wheel_install"))
    if records[-1]["returncode"]:
        raise RuntimeError("locked_install_failed")
    manifest = {"cycle_id": "M6-SHAPE-TRAIN-001", "python": str(python), "base_python": sys.executable,
                "wheel_source": "https://download.pytorch.org/whl/cpu", "numpy_source": "https://pypi.org/simple",
                "wheels": wheel_records, "processes": records, "setup_outer_wall_s": time.perf_counter() - started,
                "downloaded_wheel_bytes": sum(wheel["bytes"] for wheel in wheel_records),
                "venv_bytes": sum(file.stat().st_size for file in (private / "venv").rglob("*") if file.is_file()),
                "shared_environment_changes": 0}
    (HERE / "ENVIRONMENT_LOCK.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
