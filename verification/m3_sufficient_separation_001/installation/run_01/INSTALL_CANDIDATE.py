"""Install one frozen candidate into a new release; never activate MCP or Hooks.

Adapted from verification/fixes/20261103_review_cycle004/INSTALL_CANDIDATE.py.
The source copy, Git commit and prebuilt bundle must identify the same bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile


sys.dont_write_bytecode = True
ENTRY_TEMPLATE = "examples/agents/target_runtime_entry.py"
ADMIN_TEMPLATE = "examples/agents/installed_release.py"
BUILDER = "verification/build_candidate_release.py"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def git(repository, *args):
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
    ).stdout


def replace_one(text, pattern, replacement, *, flags=re.M):
    text, count = re.subn(pattern, lambda _: replacement, text, flags=flags)
    require(count == 1, "Template changed; expected one match: " + pattern)
    return text


def install(args):
    source = args.source_root.resolve(strict=True)
    repository = args.git_repository.resolve(strict=True)
    bundle = args.bundle.resolve(strict=True)
    python = args.dependency_python.resolve(strict=True)
    release = args.release_dir.resolve()
    evidence = (args.evidence_dir or Path(__file__).parent / args.version).resolve()
    require(re.fullmatch(r"[0-9a-f]{40}", args.commit), "Pass the full fixed Git commit SHA")
    require(git(repository, "rev-parse", args.commit + "^{commit}").decode().strip() == args.commit,
            "Commit could not be resolved exactly")
    require(re.fullmatch(r"[0-9]+(?:\.[0-9]+)*(?:\+[a-z0-9]+(?:\.[a-z0-9]+)*)?", args.version),
            "Invalid release version")
    require(release.name == args.version and release.parent.name == "releases"
            and release.parent.parent.name == ".human-eye",
            "Release must be <project>/.human-eye/releases/<version>")
    require(not release.exists() or (release.is_dir() and not any(release.iterdir())),
            "Refusing to overwrite a nonempty release: " + str(release))
    require(not evidence.exists(), "Use a new evidence directory: " + str(evidence))
    require(python.is_file(), "Dependency Python must be an existing executable")

    # Compile the fixed builder bytes directly; do not import a helper from pyc.
    builder_bytes = git(repository, "show", args.commit + ":" + BUILDER)
    require((source / BUILDER).read_bytes() == builder_bytes, "Builder differs from fixed commit")
    builder = {"__name__": "_fixed_candidate_builder", "__file__": str(source / BUILDER)}
    exec(compile(builder_bytes, str(source / BUILDER), "exec", dont_inherit=True), builder)
    build_raw = (bundle / "BUILD.json").read_bytes()
    build = json.loads(build_raw)
    identity = build["runtime_identity"]
    manifest = identity["source_files"]
    require(build["distribution_version"] == args.version, "Bundle version differs")
    paths = [builder["safe_name"](row["path"]) for row in manifest]
    require(paths == sorted(set(paths)) and bool(paths), "Manifest must be nonempty, sorted and unique")
    canonical = json.dumps({"base_version": identity["base_version"],
        "implementation_revision": identity["implementation_revision"], "files": manifest},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    require(sha(canonical) == identity["source_sha256"]
            and identity["build_id"] == "sha256:" + identity["source_sha256"],
            "Bundle manifest identity differs")

    # A copied source tree need not contain .git. Check its exact needed bytes
    # against the explicit repository/commit, without changing that repository.
    needed = sorted(set(paths + [BUILDER, ENTRY_TEMPLATE, ADMIN_TEMPLATE, "pyproject.toml",
        "human_eye_plugin/plugin.json", "human_eye_plugin/mcp_config.json"]))
    commit_files = {}
    archive_raw = git(repository, "archive", "--format=tar", args.commit, "--", *needed)
    with tarfile.open(fileobj=io.BytesIO(archive_raw), mode="r:") as archive:
        for member in archive.getmembers():
            if member.name in needed:
                require(member.isfile(), "Commit source is not a regular file: " + member.name)
                commit_files[member.name] = archive.extractfile(member).read()
    require(set(commit_files) == set(needed), "Fixed commit does not contain every source input")
    for relative, raw in commit_files.items():
        require((source / relative).read_bytes() == raw, "Source differs from fixed commit: " + relative)
    for row in manifest:
        require(sha(commit_files[row["path"]]) == row["sha256"], "Manifest source mismatch: " + row["path"])

    wheels = [item for item in build["artifacts"] if item["file"].endswith(".whl")]
    require(len(wheels) == 1, "Bundle must identify one wheel")
    artifact = wheels[0]
    require(Path(artifact["file"]).name == artifact["file"], "Wheel must be directly inside bundle")
    wheel = bundle / artifact["file"]
    wheel_raw = wheel.read_bytes()
    require(sha(wheel_raw) == artifact["sha256"] and len(wheel_raw) == artifact["bytes"],
            "Wheel differs from BUILD.json")
    wheel_check = builder["verify_wheel"](wheel_raw)
    project = tomllib.loads(commit_files["pyproject.toml"].decode("utf-8"))["project"]
    expected_name, expected_wheel = builder["wheel_bytes"](source, manifest, project, args.version)
    require(expected_name == wheel.name and expected_wheel == wheel_raw,
            "Wheel differs from deterministic build of fixed source")

    expected_identity = {key: identity[key] for key in
        ("base_version", "implementation_revision", "source_sha256", "build_id")}
    expected_identity["distribution_version"] = args.version
    entry_text = commit_files[ENTRY_TEMPLATE].decode("utf-8")
    for key, expression in (("RELEASE_NAME", repr(args.version)),
            ("DEPENDENCY_PYTHON", "Path(" + repr(str(python)) + ")"),
            ("SOURCE_SHA256", repr(identity["source_sha256"]))):
        entry_text = replace_one(entry_text, r"^" + key + r" = .*$", key + " = " + expression)
    entry_text = replace_one(entry_text, r"^IDENTITY = .*?^ROOT_MODULES",
        "IDENTITY = " + repr(expected_identity) + "\nROOT_MODULES", flags=re.M | re.S)
    entry_text = replace_one(entry_text, r"len\(manifest\) != \d+", "len(manifest) != " + str(len(manifest)))
    entry_text = replace_one(entry_text, r"fixed \d+-file core", "fixed " + str(len(manifest)) + "-file core")
    entry_raw = entry_text.encode("utf-8")
    admin_text = replace_one(commit_files[ADMIN_TEMPLATE].decode("utf-8"),
        r"^_TARGET_ENTRY_SHA256 = .*$", "_TARGET_ENTRY_SHA256 = " + repr(sha(entry_raw)))
    admin_raw = admin_text.encode("utf-8")
    compile(entry_raw, "target_runtime_entry.py", "exec", dont_inherit=True)
    compile(admin_raw, "installed_release.py", "exec", dont_inherit=True)

    # No default configuration or dedicated owned/reference wrapper is changed.
    evidence.mkdir(parents=True, exist_ok=False)
    release.mkdir(parents=True, exist_ok=True)
    site, admin = release / "site-packages", release / "admin"
    site.mkdir()
    admin.mkdir()
    with zipfile.ZipFile(io.BytesIO(wheel_raw)) as archive:
        archive.extractall(site)
        require(all((site / name).read_bytes() == archive.read(name) for name in archive.namelist()),
                "Installed wheel member differs")
    require(all((site / relative).read_bytes() == commit_files[relative] for relative in paths),
            "Installed source differs from the fixed commit")
    entry = admin / "target_runtime_entry.py"
    entry.write_bytes(entry_raw)
    (admin / "installed_release.py").write_bytes(admin_raw)
    binding = dict(schema_version="1.0", kind="human_eye_fixed_target_runtime",
        target_release=str(release), site_packages=str(site), dependency_python=str(python),
        launcher_sha256=sha(entry_raw), admin_sha256=sha(admin_raw),
        identity=expected_identity, source_files=manifest)
    write_json(admin / "RUNTIME_BINDING.json", binding)

    # This is a new isolated interpreter, not a proof from installer imports.
    result = subprocess.run([str(python), "-I", "-B", str(entry), "identity"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    (evidence / "INSTALLED_IDENTITY_STDOUT.json").write_bytes(result.stdout)
    (evidence / "INSTALLED_IDENTITY_STDERR.txt").write_bytes(result.stderr)
    require(result.returncode == 0, "Isolated identity failed; inspect the retained stdout/stderr")
    actual = json.loads(result.stdout)
    actual_identity = actual["runtime_identity"]
    require(all(actual_identity.get(key) == value for key, value in expected_identity.items())
            and actual_identity.get("source_kind") == "installed_distribution"
            and actual_identity.get("source_files") == manifest,
            "Isolated installed identity differs")
    require(Path(actual["python"]).resolve() == python
            and actual["launcher"]["source_file_count"] == len(manifest)
            and actual["launcher"]["launcher_sha256"] == sha(entry_raw),
            "Isolated interpreter/bootstrap differs")
    receipt = dict(status="passed", fixed_commit=args.commit, source_root=str(source),
        git_repository=str(repository), bundle=str(bundle), build_sha256=sha(build_raw),
        distribution_version=args.version, release=str(release), entry=str(entry),
        dependency_python=str(python), source_sha256=identity["source_sha256"],
        source_count=len(manifest), wheel_sha256=sha(wheel_raw), wheel_verification=wheel_check,
        source_commit_wheel_install_equal=True, isolated_identity_passed=True,
        generated_admin_files=["target_runtime_entry.py", "installed_release.py", "RUNTIME_BINDING.json"],
        launcher_sha256=sha(entry_raw), admin_sha256=sha(admin_raw),
        binding_sha256=sha((admin / "RUNTIME_BINDING.json").read_bytes()),
        default_activation_changed=False, owned_reference_changed=False)
    write_json(evidence / "ISOLATED_INSTALL.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="Frozen source copy from --commit")
    parser.add_argument("--git-repository", type=Path, required=True, help="Read-only repository containing --commit")
    parser.add_argument("--commit", required=True, help="Full fixed commit SHA, not a moving ref")
    parser.add_argument("--bundle", type=Path, required=True, help="Existing build_candidate_release output directory")
    parser.add_argument("--version", required=True, help="Distribution/release version matching BUILD.json")
    parser.add_argument("--release-dir", type=Path, required=True, help="New <project>/.human-eye/releases/<version>")
    parser.add_argument("--dependency-python", type=Path, required=True, help="Existing bound dependency interpreter")
    parser.add_argument("--evidence-dir", type=Path, help="New evidence directory; defaults to script-dir/version")
    install(parser.parse_args())


if __name__ == "__main__":
    main()
