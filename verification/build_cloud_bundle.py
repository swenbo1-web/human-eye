"""Build an allowlisted, portable source + wheel upload bundle.

The project source and previous experimental artifacts are never rewritten.
Only guarded legacy machine-specific import fallbacks are removed in the copy.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "deployment/cloud"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_python(args, cwd):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-B", *args], cwd=cwd, env=env,
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def remove_machine_fallbacks(source):
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    spans = []
    for node in tree.body:
        if (isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                and node.target.id in ("_cand", "_cand_dir")
                and any(isinstance(value, ast.Constant) and isinstance(value.value, str)
                        and value.value.startswith("D:") for value in ast.walk(node.iter))):
            spans.append((node.lineno - 1, node.end_lineno))
    for start, end in reversed(spans):
        lines[start:end] = ["# Portable distribution: use package-relative imports and the installed environment.\n"]
    result = "".join(lines)
    ast.parse(result)
    return result, len(spans)


def main():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    name = "human_eye_engine_cloud_" + version.replace(".", "_")
    artifact_root = ROOT / "artifacts"
    artifact_root.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="cloud_bundle_", dir=artifact_root))
    bundle = stage / name
    bundle.mkdir()
    source = bundle / "source"
    source.mkdir()
    source_names = [item + ".py" for item in project["tool"]["setuptools"]["py-modules"]]
    for package in project["tool"]["setuptools"]["packages"]:
        source_names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / package).glob("*.py"))]
    assert len(source_names) == 18
    edits = []
    origin = {}
    for relative in sorted(source_names):
        origin[relative] = digest(ROOT / relative)
        content, removed = remove_machine_fallbacks((ROOT / relative).read_text(encoding="utf-8"))
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        if removed:
            edits.append({"file": relative, "removed_legacy_import_fallbacks": removed})
    assert sum(item["removed_legacy_import_fallbacks"] for item in edits) == 5
    for relative in ("README.md", "Dockerfile", ".dockerignore", "requirements.lock.txt",
                     "mcp_config.json", "verify_bundle.py", "examples/sdk_smoke.py"):
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TEMPLATES / relative, target)
    shutil.copy2(ROOT / "pyproject.toml", source / "pyproject.toml")
    shutil.copy2(TEMPLATES / "README.md", source / "README.md")
    for relative in ("plugin.json",):
        shutil.copy2(ROOT / "human_eye_plugin" / relative, source / "human_eye_plugin" / relative)
    shutil.copy2(TEMPLATES / "mcp_config.json", source / "human_eye_plugin/mcp_config.json")
    wheels = bundle / "wheels"
    wheels.mkdir()
    build_log = run_python(["-m", "pip", "wheel", str(source), "--no-deps", "--wheel-dir", str(wheels),
                            "--disable-pip-version-check"], stage)
    (ROOT / "verification/cloud_bundle_build.log").write_text(build_log, encoding="utf-8")
    # Building may create local build metadata. Ship only the explicit source list.
    allowed = {*source_names, "pyproject.toml", "README.md", "human_eye_plugin/plugin.json",
               "human_eye_plugin/mcp_config.json"}
    for path in sorted(source.rglob("*"), reverse=True):
        if path.is_file() and path.relative_to(source).as_posix() not in allowed:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    wheel = next(wheels.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        for relative in source_names:
            assert archive.read(relative) == (source / relative).read_bytes(), relative
        assert json.loads(archive.read("human_eye_plugin/mcp_config.json"))["mcpServers"]["human-eye-spatial-plugin"]["command"] == "python"

    installed = Path(tempfile.mkdtemp(prefix="cloud_wheel_check_", dir=artifact_root))
    run_python(["-m", "pip", "install", "--no-deps", "--no-compile", "--target", str(installed),
                str(wheel), "--disable-pip-version-check"], stage)
    test_files = list((ROOT / "verification").glob("test_*.py")) + [
        ROOT / "verification/blind_test/geometry.py",
        ROOT / "verification/blind_test/runs/20261021_01/private/cases.json"]
    for file in test_files:
        target = installed / file.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    verification = run_python(["-c", """import io,json,pathlib,sys,unittest
import human_eye_plugin,human_eye_foveated_renderer,module_3_3_closed_loop_control_engine
for mod in (human_eye_plugin,human_eye_foveated_renderer,module_3_3_closed_loop_control_engine):
    assert pathlib.Path(mod.__file__).is_relative_to(pathlib.Path.cwd()),mod.__file__
stream=io.StringIO()
result=unittest.TextTestRunner(stream=stream).run(unittest.defaultTestLoader.discover('verification'))
print(json.dumps({'version':human_eye_plugin.__version__,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful(),'detail':stream.getvalue()}))
sys.exit(not result.wasSuccessful())
"""], installed)
    result = json.loads(verification)
    shutil.copy2(bundle / "examples/sdk_smoke.py", installed / "sdk_smoke.py")
    smoke = json.loads(run_python(["sdk_smoke.py"], installed))
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    stdio = subprocess.run([sys.executable, "-B", "-m", "human_eye_plugin.mcp_server"], cwd=installed,
                           env=env, input="".join(json.dumps(r) + "\n" for r in requests),
                           capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert stdio.returncode == 0 and not stdio.stderr, stdio.stderr
    replies = [json.loads(line) for line in stdio.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2]
    assert len(replies[1]["result"]["tools"]) == 6
    result.update(sdk_smoke=smoke, stdio_handshake_passed=True, public_tools=6,
                  linux_container_executed=False, platform=sys.platform)
    build_info = {"version": version, "distribution": "portable cloud source and wheel",
                  "source_files": len(source_names), "origin_source_sha256": origin,
                  "portable_copy_edits": edits,
                  "config_change": "portable Python module launcher, no machine cwd/environment",
                  "validation": result}
    (bundle / "BUILD_INFO.json").write_text(json.dumps(build_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Only allowlisted templates, runtime source and the new wheel enter the upload.
    banned_names = {"auth.json", "AGENTS.md", ".codex", ".agents", "verification", "__pycache__"}
    for path in bundle.rglob("*"):
        assert not any(part in banned_names for part in path.relative_to(bundle).parts), path
        if path.is_file() and path.suffix in (".py", ".json", ".md", ".toml"):
            text = path.read_text(encoding="utf-8")
            assert "D:\\hefe" not in text and "D:\\下载" not in text and "C:\\Users" not in text, path
    inventory = {p.relative_to(bundle).as_posix(): digest(p) for p in sorted(bundle.rglob("*")) if p.is_file()}
    (bundle / "MANIFEST.json").write_text(json.dumps({"version": version, "files": inventory}, indent=2) + "\n", encoding="utf-8")
    run_python(["verify_bundle.py"], bundle)
    destination = ROOT / "dist" / (name + ".zip")
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                archive.write(path, name + "/" + path.relative_to(bundle).as_posix())
    with zipfile.ZipFile(destination) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        for relative in inventory:
            assert hashlib.sha256(archive.read(name + "/" + relative)).hexdigest() == inventory[relative]
    summary = {"file": destination.name, "bytes": destination.stat().st_size, "sha256": digest(destination),
               "version": version, "files": len(inventory) + 1, "source_files": len(source_names),
               "tests": result["tests"], "passed": result["passed"], "stdio_handshake_passed": True,
               "linux_container_executed": False}
    (ROOT / "dist" / (name + "_manifest.json")).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (ROOT / "verification/cloud_bundle_check_results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
