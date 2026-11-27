"""Freeze and install isolated 041 runtime sets from verified Git bytes."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
REPO = Path("C:/Users/Administrator/.codex/worktrees/1212/hefe")
BASE = "6c93f2375d1073b33e721a168f1fcf610ac6dbdc"
R3 = "119327bbb4e645c5de3bfbc0d30259736b9a2677"
REPAIR = "31792523ecb48a500b8eed0ecb531c7ecc8e767e"
OLD = Path("D:/he_m3_bvh032_private_654c1f69/.human-eye/releases/9.7.2+b32g")
HOOK = "human_eye_hook.py"
KERNEL_FILES = {"human_eye_plugin/surface_proximity.py", "human_eye_plugin/surface_geometry.py",
                "human_eye_plugin/surface_scan.py", "human_eye_plugin/task_query.py"}
BUILD = "verification/build_candidate_release.py"
PACKAGE_FILES = ("pyproject.toml", "README.md", BUILD, "human_eye_plugin/plugin.json", "human_eye_plugin/mcp_config.json")


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def artifact(path):
    return dict(path=str(path.resolve()), bytes=path.stat().st_size, sha256=sha(path.read_bytes()))


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as target:
        json.dump(value, target, indent=2, ensure_ascii=False, allow_nan=False)
        target.write("\n")


def git_blobs(items):
    queries = [f"{ref}:{path}" for ref, path in items]
    raw = subprocess.run(["git", "-C", str(REPO), "cat-file", "--batch"],
                         input=("\n".join(queries) + "\n").encode("utf-8"),
                         capture_output=True, check=True, timeout=60).stdout
    blobs, offset = {}, 0
    for item in items:
        line_end = raw.index(b"\n", offset)
        digest, kind, count = raw[offset:line_end].split()
        assert kind == b"blob"
        size = int(count)
        content = raw[line_end + 1:line_end + 1 + size]
        assert raw[line_end + 1 + size:line_end + 2 + size] == b"\n"
        assert hashlib.sha1(b"blob " + count + bytes([0]) + content).hexdigest().encode() == digest
        blobs[item] = content
        offset = line_end + 2 + size
    assert offset == len(raw)
    return blobs


def canonical(version, revision, files):
    body = dict(base_version=version, implementation_revision=revision, files=files)
    return sha(json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode())


def patch(source, before, after, count):
    needle = before.encode()
    assert source.count(needle) == count
    return source.replace(needle, after.encode())


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, path
        return
    with path.open("xb") as stream:
        stream.write(raw)


def main():
    baseline = json.loads((OLD / "admin/RUNTIME_BINDING.json").read_bytes())
    py = Path(baseline["dependency_python"])
    manifest = baseline["source_files"]
    paths = [row["path"] for row in manifest]
    assert len(paths) == len(set(paths)) == 143 and paths == sorted(paths)
    assert not set(PACKAGE_FILES) & set(paths)
    for ref in (BASE, R3):
        all_names = subprocess.check_output(["git", "-C", str(REPO), "ls-tree", "-r", "--name-only", ref], timeout=45).decode().splitlines()
        package_sources = {n for n in all_names if PurePosixPath(n).parent.as_posix()
                           in {"human_eye_plugin", "human_eye_module1_operators"} and n.endswith(".py")}
        assert package_sources == {n for n in paths if "/" in n}
    delta = subprocess.check_output(["git", "-C", str(REPO), "diff", "--name-only", BASE, R3, "--"] + paths, timeout=25).decode().splitlines()
    assert set(delta) == KERNEL_FILES
    repair_delta = subprocess.check_output(["git", "-C", str(REPO), "diff", "--name-only", BASE, REPAIR], timeout=25).decode().splitlines()
    assert repair_delta == [HOOK]
    data = git_blobs([(ref, p) for ref in (BASE, R3) for p in (*paths, *PACKAGE_FILES)] + [(REPAIR, HOOK)])
    build_template = baseline["identity"]
    base_v, revision = (build_template[k] for k in ("base_version", "implementation_revision"))
    expected_authors = {
        "032": "0f9e6336ec54adf9e7b9a5379b02d2c2cab9f6d1f734138c3fde29e08ccee241",
        "r3": "eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4",
    }
    for row in manifest:
        p = row["path"]
        assert (OLD / "site-packages" / p).read_bytes() == data[BASE, p]
        assert sha(data[BASE, p]) == row["sha256"]
    assert all(data[BASE, p] == data[R3, p] for p in PACKAGE_FILES)
    original_launcher = (OLD / "admin/target_runtime_entry.py").read_bytes()
    original_manager = (OLD / "admin/installed_release.py").read_bytes()
    assert sha(original_launcher) == baseline["launcher_sha256"] and sha(original_manager) == baseline["admin_sha256"]
    all_arms = {}
    for name, ref in (("032", BASE), ("r3", R3)):
        home = ROOT / name
        home.mkdir(exist_ok=True)
        unmodified = [dict(path=p, sha256=sha(data[ref, p])) for p in paths]
        original_sha = canonical(base_v, revision, unmodified)
        assert original_sha == expected_authors[name], (name, original_sha)
        source = home / "source"
        for p in (*paths, *PACKAGE_FILES):
            put(source / p, data[(REPAIR if p == HOOK else ref), p])
        sources = [dict(path=p, sha256=sha((source / p).read_bytes())) for p in paths]
        integrated = canonical(base_v, revision, sources)
        changed = {p for p in paths if (source / p).read_bytes() != data[BASE, p]}
        assert changed == ({HOOK} if name == "032" else {HOOK} | KERNEL_FILES)
        edition = "9.7.2+k041hook032" if name == "032" else "9.7.2+k041hookr3"
        build_path = home / "build/BUILD.json"
        if not build_path.exists():
            result = subprocess.run([str(py), "-I", "-B", str(source / BUILD), "--output", str(home / "build"),
                                     "--version", edition], cwd=source, capture_output=True, timeout=90)
            for category, content in (("stdout", result.stdout), ("stderr", result.stderr)):
                put(home / f"BUILDER.{category}", content)
            result.check_returncode()
        build = json.loads(build_path.read_bytes())
        assert build["runtime_identity"]["source_files"] == sources and build["runtime_identity"]["source_sha256"] == integrated
        assert build["deterministic_rebuild"]
        wheel_ref = next(art for art in build["artifacts"] if art["file"].endswith(".whl"))
        wheel = home / "build" / wheel_ref["file"]
        assert artifact(wheel)["sha256"] == wheel_ref["sha256"]
        release = home / ".human-eye/releases" / edition
        site = release / "site-packages"
        with ZipFile(wheel) as archive:
            assert len(archive.namelist()) == len(set(archive.namelist()))
            for p in archive.namelist():
                rel = PurePosixPath(p)
                assert not rel.is_absolute() and ".." not in rel.parts and ":" not in p and chr(92) not in p
                put(site / Path(*rel.parts), archive.read(p))
        assert all((site / p).read_bytes() == (source / p).read_bytes() for p in paths)
        admin = release / "admin"
        launcher = patch(original_launcher, build_template["distribution_version"], edition, 2)
        launcher = patch(launcher, build_template["source_sha256"], integrated, 3)
        manager = patch(original_manager, baseline["launcher_sha256"], sha(launcher), 1)
        identity = {key: build["runtime_identity"][key] for key in build_template}
        identity["distribution_version"] = edition
        binding = dict(baseline, target_release=str(release.resolve()), site_packages=str(site.resolve()),
                       launcher_sha256=sha(launcher), admin_sha256=sha(manager), identity=identity, source_files=sources)
        binding_path = admin / "RUNTIME_BINDING.json"
        put(admin / "target_runtime_entry.py", launcher)
        put(admin / "installed_release.py", manager)
        put(binding_path, (json.dumps(binding, indent=2) + "\n").encode("utf-8"))
        run = subprocess.run([str(py), "-I", "-B", str(admin / "target_runtime_entry.py"), "identity"],
                             cwd=home, capture_output=True, timeout=30)
        put(home / "STARTUP.stdout.json", run.stdout)
        put(home / "STARTUP.stderr", run.stderr)
        run.check_returncode()
        assert not run.stderr
        startup = json.loads(run.stdout)
        assert all(startup["runtime_identity"][k] == v for k,v in identity.items())
        assert startup["launcher"]["binding_sha256"] == artifact(binding_path)["sha256"]
        receipt = {"kernel_source_commit": ref, "common_hook_repair_commit": REPAIR,
                   "old_source_sha256": original_sha, "source_sha256": integrated,
                   "site": str(site.resolve()), "dependency_python": str(py.resolve()),
                   "release": str(release.resolve()), "identity": identity,
                   "binding": artifact(binding_path), "launcher": artifact(admin / "target_runtime_entry.py"),
                   "admin": artifact(admin / "installed_release.py"),
                   "startup": artifact(home / "STARTUP.stdout.json"), "build": artifact(build_path),
                   "wheel": artifact(wheel), "source_count": len(sources),
                   "changes_from_032": {p: {"before_sha256": sha(data[BASE, p]), "after_sha256": sha((source / p).read_bytes())}
                                        for p in sorted(changed)},
                   "common_hook_sha256": sha(data[REPAIR, HOOK]),
                   "source_manifest": sources}
        save(home / "READY.json", receipt)
        all_arms[name] = receipt
        print(name, integrated, release, flush=True)
    m0, m1 = ({row["path"]: row["sha256"] for row in all_arms[i]["source_manifest"]} for i in ("032", "r3"))
    assert {p for p in paths if m0[p] != m1[p]} == KERNEL_FILES
    save(ROOT / "PINS.json", {"schema": "m6-041-installed-runtime-pins-v1", "status":"verified_isolated",
                             "releases": {k: v["release"] for k, v in all_arms.items()},
                             "binding": {k: v["binding"] for k, v in all_arms.items()},
                             "identities": {k: v["identity"] for k, v in all_arms.items()},
                             "arms": all_arms, "source_changes_between_arms": sorted(KERNEL_FILES),
                             "original_base": artifact(OLD / "admin/RUNTIME_BINDING.json"),
                             "builder": artifact(Path(__file__)),
                             "production_modified": False, "ndarray_conversion_added":False})
    print(artifact(ROOT / "PINS.json"), flush=True)


if __name__ == "__main__":
    main()