"""Install the single frozen 043 queue-order candidate beside the real 041 R3.

No product activation, dependency installation, Blender, or measurement occurs.
Only the literal managed candidate directory below is writable by this builder.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/candidate")
OLD_HOME = Path("D:/HumanEye/runs/M6-041-KERNEL-HOOK/install/r3")
OLD = OLD_HOME / ".human-eye/releases/9.7.2+k041hookr3"
EDITION = "9.7.2+k043region"
OLD_SOURCE_SHA = "ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e"
OLD_BINDING_SHA = "f2997b776fb12e119851c876ee9519588e2edf929ce90f282b2ba1899e8c6546"
OLD_LAUNCHER_SHA = "888c8774bc2d06c9c2f2f9ef5bec18902153c3a784df862737056708180b25c7"
OLD_ADMIN_SHA = "b9049ff3fa599a07abc982233ed2aa1c3ae3e2167f9da530e7ee7492feacc41a"
KERNEL = "human_eye_plugin/surface_proximity.py"
BUILD = "verification/build_candidate_release.py"
EXTRAS = ("pyproject.toml", "README.md", BUILD,
          "human_eye_plugin/plugin.json", "human_eye_plugin/mcp_config.json")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def artifact(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=sha(raw))


def put(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, ("refuse_changed_existing_artifact", str(path))
    else:
        with path.open("xb") as stream:
            stream.write(raw)


def save(path, value):
    put(path, (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode())


def replace_exact(raw, before, after, count):
    before, after = before.encode(), after.encode()
    assert raw.count(before) == count, (before, raw.count(before), count)
    return raw.replace(before, after)


def candidate_bytes(raw):
    source = raw.decode("utf-8")
    # Existing roots are exact world-integer (lo, hi, count, ids, children).
    # No bounding arithmetic, geometry mutation, extra work charge, or pruning.
    first = "    shift = max(0, span_bits - (MAX_BITS - 1))\n"
    after = first + (
        "    contained_zero_fifo = shift == 0 and (\n"
        "        all(roots[0][0][axis] < roots[1][0][axis]\n"
        "            and roots[1][1][axis] < roots[0][1][axis] for axis in range(3))\n"
        "        or all(roots[1][0][axis] < roots[0][0][axis]\n"
        "               and roots[0][1][axis] < roots[1][1][axis] for axis in range(3))\n"
        "    )\n")
    second = "        heapq.heappush(pending, (key, cdist, serial, sl, sr))\n"
    second_after = (
        "        secondary = 0 if contained_zero_fifo and key == 0 else cdist\n"
        "        heapq.heappush(pending, (key, secondary, serial, sl, sr))\n")
    assert source.count(first) == source.count(second) == 1
    changed = source.replace(first, after).replace(second, second_after)
    assert changed.replace(after, first).replace(second_after, second) == source
    before_ast, after_ast = ast.parse(source), ast.parse(changed)
    before_nodes = {node.name: ast.dump(node) for node in before_ast.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    after_nodes = {node.name: ast.dump(node) for node in after_ast.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    assert before_nodes.keys() == after_nodes.keys()
    assert {name for name in before_nodes if before_nodes[name] != after_nodes[name]} == {"_nearest_tree"}
    return changed.encode("utf-8")


def main():
    assert RAW.resolve() == RAW and HERE.name == "candidate"
    baseline_ref = artifact(OLD / "admin/RUNTIME_BINDING.json")
    assert baseline_ref["sha256"] == OLD_BINDING_SHA
    baseline = json.loads((OLD / "admin/RUNTIME_BINDING.json").read_bytes())
    assert baseline["identity"]["source_sha256"] == OLD_SOURCE_SHA
    assert baseline["launcher_sha256"] == OLD_LAUNCHER_SHA
    assert baseline["admin_sha256"] == OLD_ADMIN_SHA
    for filename, expected in (("target_runtime_entry.py", OLD_LAUNCHER_SHA),
                               ("installed_release.py", OLD_ADMIN_SHA)):
        assert sha((OLD / "admin" / filename).read_bytes()) == expected
    rows = baseline["source_files"]
    paths = [row["path"] for row in rows]
    assert len(paths) == 143 and paths == sorted(set(paths))
    old_sources = {}
    for row in rows:
        p = row["path"]
        assert PurePosixPath(p).as_posix() == p and ".." not in PurePosixPath(p).parts
        old_sources[p] = (OLD / "site-packages" / p).read_bytes()
        assert sha(old_sources[p]) == row["sha256"], p
    new_kernel = candidate_bytes(old_sources[KERNEL])
    patch = "".join(difflib.unified_diff(old_sources[KERNEL].decode().splitlines(True),
                                      new_kernel.decode().splitlines(True),
                                      fromfile="a/" + KERNEL, tofile="b/" + KERNEL))
    put(HERE / "C.patch", patch.encode())
    put(RAW / "C.patch", patch.encode())
    source = RAW / "source"
    for p, raw in old_sources.items():
        put(source / p, new_kernel if p == KERNEL else raw)
    extras_refs = {}
    for p in EXTRAS:
        original = OLD_HOME / "source" / p
        put(source / p, original.read_bytes())
        extras_refs[p] = artifact(original)
    sources = [dict(path=p, sha256=sha((source / p).read_bytes())) for p in paths]
    changed = [row["path"] for row, old in zip(sources, rows) if row != old]
    assert changed == [KERNEL]
    py = Path(baseline["dependency_python"])
    build_path = RAW / "build/BUILD.json"
    if not build_path.exists():
        run = subprocess.run([str(py), "-I", "-B", str(source / BUILD),
                              "--output", str(RAW / "build"), "--version", EDITION],
                             cwd=source, capture_output=True, timeout=90)
        put(RAW / "BUILDER.stdout", run.stdout)
        put(RAW / "BUILDER.stderr", run.stderr)
        run.check_returncode()
    build = json.loads(build_path.read_bytes())
    assert build["runtime_identity"]["source_files"] == sources and build["deterministic_rebuild"]
    new_sha = build["runtime_identity"]["source_sha256"]
    assert new_sha != OLD_SOURCE_SHA
    wheel_row = next(r for r in build["artifacts"] if r["file"].endswith(".whl"))
    wheel = RAW / "build" / wheel_row["file"]
    assert artifact(wheel)["sha256"] == wheel_row["sha256"]
    release = RAW / ".human-eye/releases" / EDITION
    site = release / "site-packages"
    with ZipFile(wheel) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        for p in archive.namelist():
            rel = PurePosixPath(p)
            assert not rel.is_absolute() and ".." not in rel.parts and ":" not in p and "\\" not in p
            put(site / Path(*rel.parts), archive.read(p))
    assert all((site / p).read_bytes() == (source / p).read_bytes() for p in paths)
    launcher = (OLD / "admin/target_runtime_entry.py").read_bytes()
    launcher = replace_exact(launcher, baseline["identity"]["distribution_version"], EDITION, 2)
    launcher = replace_exact(launcher, OLD_SOURCE_SHA, new_sha, 3)
    manager = replace_exact((OLD / "admin/installed_release.py").read_bytes(), OLD_LAUNCHER_SHA, sha(launcher), 1)
    identity = {key: build["runtime_identity"][key] for key in baseline["identity"] if key != "distribution_version"}
    identity["distribution_version"] = EDITION
    binding = dict(baseline, target_release=str(release.resolve()), site_packages=str(site.resolve()),
                   launcher_sha256=sha(launcher), admin_sha256=sha(manager),
                   identity=identity, source_files=sources)
    admin = release / "admin"
    put(admin / "target_runtime_entry.py", launcher)
    put(admin / "installed_release.py", manager)
    save(admin / "RUNTIME_BINDING.json", binding)
    run = subprocess.run([str(py), "-I", "-B", str(admin / "target_runtime_entry.py"), "identity"],
                         cwd=RAW, capture_output=True, timeout=30)
    put(RAW / "STARTUP.stdout.json", run.stdout)
    put(RAW / "STARTUP.stderr", run.stderr)
    run.check_returncode()
    assert not run.stderr
    startup = json.loads(run.stdout)
    assert all(startup["runtime_identity"][k] == v for k, v in identity.items())
    assert startup["launcher"]["binding_sha256"] == artifact(admin / "RUNTIME_BINDING.json")["sha256"]
    # Recheck all baseline and installed candidate sources after the subprocess.
    assert all(sha((OLD / "site-packages" / row["path"]).read_bytes()) == row["sha256"] for row in rows)
    assert all(sha((site / row["path"]).read_bytes()) == row["sha256"] for row in sources)
    pins = dict(schema="m6-043-single-source-candidate-v1", status="installed_identity_verified",
                baseline_binding=baseline_ref, baseline_release=str(OLD),
                baseline_source_sha256=OLD_SOURCE_SHA,
                source_sha256=new_sha, source_count=len(sources), source_manifest=sources,
                changes_from_installed_r3={KERNEL: dict(before_sha256=sha(old_sources[KERNEL]),
                                                      after_sha256=sha(new_kernel))},
                site=str(site), source=str(source), release=str(release), dependency_python=str(py),
                identity=identity, binding=artifact(admin / "RUNTIME_BINDING.json"),
                launcher=artifact(admin / "target_runtime_entry.py"),
                admin=artifact(admin / "installed_release.py"), startup=artifact(RAW / "STARTUP.stdout.json"),
                patch=artifact(HERE / "C.patch"), builder=artifact(Path(__file__)),
                original_packaging_sources=extras_refs, build=artifact(build_path), wheel=artifact(wheel),
                product_activated=False, blender_launched=False, official_timing_run=False)
    save(RAW / "PINS.json", pins)
    save(HERE / "PINS.json", pins)
    print(json.dumps(dict(status=pins["status"], site=str(site), source_sha256=new_sha,
                          kernel_sha256=sha(new_kernel), pins=artifact(RAW / "PINS.json"))))


if __name__ == "__main__":
    main()
