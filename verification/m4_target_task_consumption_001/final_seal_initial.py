"""Seal fixed sources and saved task evidence, then verify exact Git closure."""

import argparse
from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = Path("D:/he_m4_target_consume_001").resolve()
BASELINE = "71a505135ecf202c0e8572fb01bbe21c410342e2"
PRODUCT_GIT = "c309d7e4302518cd5f7d1c3966e7c7fa338ea128"
PRODUCT_SHA = "776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be"
WHEEL_SHA = "aefa75ab15aa47632ecb16f6a59af207186e2b66ced9a5baa2253ec55eb36486"
ORDER = ["N1", "P1", "P2", "N2", "N3", "P3"]
FIXED = {
    "BASELINE.json": "947419de5dd30e584a02955ad6757bb5eb57a95e2bf40fbf0b9cc3177061a738",
    "FROZEN.json": "1ca70cca59b160ee02f34e4eaf479ff0933fd4fb46560a888d89a100a184cb3f",
    "PREPARED.json": "8e679cf5e13e2500f7d5632776041ff47edb5ba6bb39f707d8ca7f081bc43371",
    "admin/PRIVATE_SOURCE_FREEZE.json": "a722cf277f079feba224f0b14a106fbf111e058d66f2aeaf1c7041294b7f850b",
    "admin/SCORING_CONTRACT.json": "c1cc6122d694db0f330e3c8cf487219fa30d07cc3b96d3a0790930161a7b329c",
}


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(value, label):
    if not value:
        raise AssertionError(label)


def dump(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def pins(rows, root=ROOT):
    seen = set()
    for row in rows:
        path = Path(row["path"])
        path = path if path.is_absolute() else root / path
        key = str(path.resolve())
        require(key not in seen, "duplicate pin path")
        seen.add(key)
        require(sha(path) == row["sha256"], "changed pinned bytes " + key)
        if "bytes" in row:
            require(path.stat().st_size == row["bytes"], "changed pinned size " + key)
    return len(seen)


def mapping_pins(mapping, root=ROOT):
    return pins([{"path": name, "sha256": digest} for name, digest in mapping.items()], root)


def files_under(directory):
    directory = Path(directory).resolve()
    paths = []
    for current, names, files in os.walk(directory, topdown=True, followlinks=False):
        for name in names + files:
            path = Path(current) / name
            require(not path.is_symlink() and not path.is_junction(), "unexpected reparse entry")
            path.resolve().relative_to(directory)
        if directory == HERE:
            names[:] = [name for name in names if name != "__pycache__"]
        paths.extend(Path(current) / name for name in files)
    return sorted(paths)


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def tree_objects(commit):
    values = {}
    for row in git("ls-tree", "-rz", commit).split(b"\0"):
        if row:
            fields, path = row.split(b"\t", 1)
            values[path.decode("utf-8")] = fields.split()[2].decode("ascii")
    return values


def verify_sources():
    for name, digest in FIXED.items():
        require(sha(HERE / name) == digest, "original freeze changed " + name)
    base = read(HERE / "BASELINE.json")
    require(base["baseline_git"] == BASELINE and base["product_git"] == PRODUCT_GIT
            and base["product_source141_sha256"] == PRODUCT_SHA, "baseline identity")
    require(len(base["protected_old_pins"]) == 23, "protected old pin count")
    old_members = 0
    for name, digest in base["protected_old_pins"].items():
        require(sha(name) == digest, "protected old evidence changed " + name)
        if Path(name).name == "CONTENT_MANIFEST.json":
            old_members += pins(read(name)["files"], Path(name).parents[2])
    for name, digest in base["references"].items():
        require(sha(name) == digest and sha(HERE / "reference" / Path(name).name) == digest,
                "original reference changed")
    frozen = read(HERE / "FROZEN.json")
    prepared = read(HERE / "PREPARED.json")
    scoring = read(HERE / "admin/PRIVATE_SOURCE_FREEZE.json")
    require(pins(frozen["files"]) == 423, "formal freeze 423 pins")
    prepared_count = pins(prepared["source_files"])
    require(mapping_pins(scoring["files_sha256"]) == 33, "original scoring 33 pins")
    require(sha(scoring["contract"]["path"]) == scoring["contract"]["sha256"]
            == FIXED["admin/SCORING_CONTRACT.json"], "scoring contract binding")
    binding = read(HERE / "PRODUCT_RUN_BINDING.json")
    require(binding["source_sha256"] == PRODUCT_SHA and binding["preparation_git"] == PRODUCT_GIT
            and Path(binding["install_root"]).resolve() == Path("D:/he_m4_target_002/B/product").resolve(), "fixed installation")
    require(pins(binding["source_manifest"]) == pins(binding["source_manifest"], Path(binding["install_root"])) == 141,
            "fixed 141 worktree and installed sources")
    identity = {name: binding[name] for name in ("base_version", "implementation_revision")}
    identity["files"] = binding["source_manifest"]
    aggregate = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    require(aggregate == PRODUCT_SHA, "product source aggregate")
    for commit in (BASELINE, PRODUCT_GIT):
        tree = tree_objects(commit)
        for row in binding["source_manifest"]:
            require(tree[row["path"]] == git_blob((ROOT / row["path"]).read_bytes()), "fixed Git product source")
    wheels = list((HERE.parent / "m4_target_acquisition_002/build_B").glob("*.whl"))
    require(len(wheels) == 1 and sha(wheels[0]) == binding["wheel_sha256"] == WHEEL_SHA, "original fixed wheel")
    with zipfile.ZipFile(wheels[0]) as wheel:
        for row in binding["source_manifest"]:
            require(hashlib.sha256(wheel.read(row["path"])).hexdigest() == row["sha256"], "fixed wheel member")
    prefix = HERE.relative_to(ROOT).as_posix() + "/"
    changed = [path.decode("utf-8") for path in git("diff", "--name-only", "-z", BASELINE).split(b"\0") if path]
    untracked = [path.decode("utf-8") for path in git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if path]
    require(all(path.startswith(prefix) for path in changed + untracked), "changes outside sole new namespace")
    return {"protected_old_pins": 23, "protected_old_manifest_members": old_members,
            "original_reference_pins": len(base["references"]), "formal_frozen_pins": 423,
            "prepared_pins": prepared_count, "scoring_pins": 33,
            "product_Git_worktree_wheel_installed_sources": 141, "product_diff_paths": []}


def verify_results():
    quality = read(HERE / "QUALITY.json")
    require(quality["schema"] == "target-task-consumption-quality-v1" and quality["denominator"] == 6,
            "six quality denominator")
    require([row["slot_id"] for row in quality["slots"]] == ORDER, "six unique quality rows")
    mapping_pins(quality["inputs_sha256"])
    seal = read(HERE / "QUALITY_SEAL.json")
    require(seal["quality_sha256"] == sha(HERE / "QUALITY.json") and seal["cost_unlocked"] is True
            and type(seal["sealed_ns"]) is int, "quality-first seal binding")
    require(seal["semantic_review_sha256"] in quality["inputs_sha256"].values(), "semantic review bound in quality inputs")
    decision = read(HERE / "DECISION.json")
    require(decision["schema"] == "target-task-consumption-decision-v1"
            and decision["quality_sha256"] == sha(HERE / "QUALITY.json")
            and decision["quality_seal_sha256"] == sha(HERE / "QUALITY_SEAL.json"), "decision quality binding")
    require(decision["decision_source_sha256"] == sha(HERE / "cost_decision.py"), "decision source binding")
    pins(decision["input_pins"])
    require(type(decision["passed_frozen_gates"]) is bool and len(decision["rows"]) == 6 and len(decision["pairs"]) == 3,
            "complete decision rows and gate state")
    checker = read(HERE / "COST_CHECKER_REVIEW.json")
    require(checker["passed_checked_scope"] is True
            and Path(checker["reviewed_source"]["path"]).resolve() == (HERE / "cost_decision.py").resolve()
            and checker["reviewed_source"]["sha256"] == decision["decision_source_sha256"],
            "cost formula/source checker binding")
    cost_review = read(HERE / "CONSUMER_COST_REVIEW.json")
    require(cost_review["passed_checked_scope"] is True, "actual consumer cost source audit")
    pins(cost_review["input_pins"])
    review = read(HERE / "RUNTIME_REVIEW.json")
    require(review["passed_checked_scope"] is True and review["qualification_only"] is False,
            "full runtime technical audit")
    pins(review["input_pins"])
    require((HERE / "REPORT.md").is_file(), "root final report")
    run = read(RUNTIME / "RUN_RESULT.json")
    intent = read(RUNTIME / "FORMAL_STARTED.json")
    require([row["slot_id"] for row in run["records"]] == ORDER and run["planned_slots"] == 6
            and run["actual_consumers"] == 6 and run["formal_batch_attempts"] == 1
            and run["outer_retries"] == run["replacement_samples"] == 0, "single six-consumer run")
    require(intent["formal_attempts"] == 1 and intent["outer_retries"] == intent["replacement_samples"] == 0
            and intent["freeze_sha256"] == FIXED["FROZEN.json"]
            and intent["plan_sha256"] == sha(HERE / "PLAN.json"), "formal start marker")
    answers = []
    for outer in run["records"]:
        slot = outer["slot_id"]
        folder = RUNTIME / "formal" / slot
        result_path, publication_path = folder / "SLOT_RESULT.json", folder / "SLOT_PUBLICATION.json"
        require(Path(outer["result_path"]).resolve() == result_path.resolve()
                and Path(outer["publication_path"]).resolve() == publication_path.resolve(), "actual slot paths")
        require(sha(result_path) == outer["result_sha256"] and sha(publication_path) == outer["publication_sha256"], "actual slot hashes")
        result, publication = read(result_path), read(publication_path)
        require(result["slot_id"] == publication["slot_id"] == slot and result["group"] == publication["group"] == slot[0], "actual slot identity")
        require(publication["result_sha256"] == sha(result_path) and publication["status"] == outer["status"], "actual publication status")
        consumer_path = folder / "consumer/CONSUMER.json"
        require(Path(result["consumer_record"]).resolve() == consumer_path.resolve(), "actual consumer path")
        consumer = read(consumer_path)
        require(type(consumer.get("consumer_pid")) is int and consumer["consumer_pid"] > 0
                and consumer.get("image_delivery", {}).get("CLI_process_launched") is True, "actual CLI launch proof")
        answer = consumer.get("final")
        public = folder / "consumer/PUBLIC_FINAL.txt"
        if answer is not None:
            require(type(answer) is str and public.read_bytes() == answer.encode("utf-8"), "original public final bytes")
        else:
            require(not public.exists(), "missing final represented honestly")
        answers.append({"slot_id": slot, "present": answer is not None, "consumer_sha256": sha(consumer_path),
                        "public_final_sha256": sha(public) if public.exists() else None})
    return {"formal_repetitions": 1, "actual_consumer_tasks": 6, "replacement_samples": 0,
            "quality_denominator": 6, "all_six_quality_complete": quality["all_six_quality_complete"],
            "N_quality_count": quality["N_quality_count"], "P_quality_count": quality["P_quality_count"],
            "P_actual_product_fact_adoption_count": quality["P_actual_product_fact_adoption_count"],
            "disposition": decision["disposition"], "passed_frozen_business_gates": decision["passed_frozen_gates"],
            "original_answers": answers}


def verify_budget_archive():
    claims = {path.stem: (path, read(path)) for path in (RUNTIME / "budget/claims").glob("*.json")}
    require(bool(claims), "actual budget claims")
    starts = Counter()
    rasters = Counter()
    business = Counter()
    expected_settlements = set()
    for token, (path, claim) in claims.items():
        require(claim["token"] == token and claim["label"] in ["N_qual", "P_qual"] + ORDER
                and claim["phase"] in ("qualification", "formal") and claim["reserved_upper_bound"] == 1, "unit budget claim")
        if claim["kind"] == "business_tool":
            business[claim["label"]] += 1
            continue
        require(claim["kind"] in ("Blender_start", "raster_attempt"), "known budget kind")
        expected_settlements.add(token)
        settled = read(RUNTIME / "budget/settlements" / (token + ".json"))
        require(settled["token"] == token and settled["claim_sha256"] == sha(path), "budget settlement source")
        if claim["kind"] == "Blender_start":
            require(settled["spawn_status"] == "spawned" and type(settled["pid"]) is int and settled["pid"] > 0, "actual owned spawn")
            starts[claim["phase"]] += 1
        else:
            require(settled["actual_attempts"] == settled["confirmed_attempts_lower_bound"] == 1, "confirmed raster attempt")
            rasters[claim["phase"]] += 1
            rasters[claim["label"]] += 1
    require({path.stem for path in (RUNTIME / "budget/settlements").glob("*.json")} == expected_settlements,
            "exact settled start/raster claims")
    require(starts["qualification"] == 2 and starts["formal"] == 6
            and rasters["qualification"] == read(HERE / "FROZEN.json")["qualification_rasters"]
            and rasters["qualification"] <= 12 and rasters["formal"] <= 36
            and rasters["qualification"] + rasters["formal"] <= 48
            and all(rasters[label] <= 6 and business[label] <= 12 for label in ["N_qual", "P_qual"] + ORDER), "fixed actual budgets")
    archive = read(HERE / "RUNTIME_ARCHIVE.json")
    require(archive["schema"] == "target-task-consumption-runtime-archive-v1"
            and Path(archive["runtime_root"]).resolve() == RUNTIME
            and archive["original_runtime_retained"] is True and archive["all_copies_verified_byte_exact"] is True
            and archive["runtime_exclusions"] == [], "complete original runtime archive contract")
    mapping_pins(archive["report_pins"], HERE)
    original = {path.relative_to(RUNTIME).as_posix(): path for path in files_under(RUNTIME)}
    require(len(archive["files"]) == archive["file_count"] and len(original) == archive["file_count"], "archive count")
    require({row["relative_path"] for row in archive["files"]} == set(original), "entire runtime archived")
    targets = set()
    for row in archive["files"]:
        source, target = original[row["relative_path"]], HERE / row["archive_path"]
        require(source.resolve() == Path(row["original_path"]).resolve()
                and target.resolve().is_relative_to(HERE / "runtime_archive"), "archive path scope")
        require(str(target.resolve()) not in targets, "duplicate archive target")
        targets.add(str(target.resolve()))
        require(source.stat().st_size == target.stat().st_size == row["bytes"]
                and sha(source) == sha(target) == row["sha256"], "archive original-byte parity")
    require(sum(row["bytes"] for row in archive["files"]) == archive["bytes"], "archive total bytes")
    require({str(path.resolve()) for path in files_under(HERE / "runtime_archive")} == targets,
            "exact archive target closure")
    return {"owned_Blender_starts": sum(starts.values()), "qualification_rasters": rasters["qualification"],
            "formal_rasters": rasters["formal"], "total_rasters": rasters["qualification"] + rasters["formal"],
            "business_admissions": dict(business), "pending_start_raster_reservations": 0,
            "runtime_archive_files": archive["file_count"], "runtime_archive_bytes": archive["bytes"],
            "original_runtime_retained": True}


def credential_scan():
    patterns = [re.compile(value) for value in (
        rb"(?<![A-Za-z0-9])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}",
        rb"gh[pousr]_[A-Za-z0-9]{30,}", rb"github_pat_[A-Za-z0-9_]{40,}", rb"AIza[A-Za-z0-9_-]{35}",
        rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
        rb"(?:access_token|refresh_token|id_token)[\"']?\s*[:=]\s*[\"'][A-Za-z0-9._~-]{24,}",
    )]
    private = {"auth.json", "credentials.json", "token.json", ".env", "id_rsa", "id_ed25519"}
    findings = []
    checked = members = 0

    def inspect(blob, label, filename):
        nonlocal checked, members
        checked += 1
        if Path(filename).name.lower() in private:
            findings.append({"path": label, "rule": "private_filename"})
        for index, pattern in enumerate(patterns, 1):
            if pattern.search(blob):
                findings.append({"path": label, "rule": "credential_pattern_" + str(index)})
        if zipfile.is_zipfile(io.BytesIO(blob)):
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                for member in archive.infolist():
                    if not member.is_dir():
                        members += 1
                        inspect(archive.read(member), label + "!" + member.filename, member.filename)

    for path in files_under(HERE) + files_under(RUNTIME):
        inspect(path.read_bytes(), str(path), path.name)
    require(not findings, "credential candidates (paths and rules only) " + json.dumps(findings, ensure_ascii=True))
    return {"credential_scan_original_and_delivery_items": checked,
            "credential_scan_container_members": members, "credential_pattern_candidates": 0,
            "credential_scan_scope": "Original bytes and recursively decoded ZIP members. Pattern scan only. Matching bytes are never printed."}


def seal():
    for name in ("FINAL_AUDIT.json", "CONTENT_MANIFEST.json", "QUALIFICATION_LEDGER.json"):
        require(not (HERE / name).exists(), "seal outputs are write once")
    checks = verify_sources()
    checks.update(verify_results())
    checks.update(verify_budget_archive())
    checks.update(credential_scan())
    base = read(HERE / "BASELINE.json")
    closed = time.perf_counter_ns()
    dump(HERE / "QUALIFICATION_LEDGER.json", {"schema": "target-task-consumption-ledger-v1",
        "registered_started_ns": base["started_ns"], "audit_closed_ns": closed,
        "registered_analysis_elapsed_ns": closed - base["started_ns"],
        "scope": "Registration through saved-only sealing. Preparation, qualifications, consumers and reviews have separate nested clocks.",
        "formal_repetitions": 1, "consumer_tasks": 6, "retries": 0, "replacement_samples": 0,
        "new_operations_by_sealer": {"Blender_starts": 0, "model_calls": 0, "rasters": 0},
        "coordinator_reviewer_fees": None, "limits": base["limits"]})
    dump(HERE / "FINAL_AUDIT.json", {"schema": "target-task-consumption-root-audit-v1",
        "passed_checked_scope": True, "baseline_git": BASELINE, "product_git": PRODUCT_GIT,
        "product_source141_sha256": PRODUCT_SHA, "administrator_review": "pending",
        "AL_registration": "pending_current_chat_host_binding", "reviewer_associations_disclosed": True,
        "business_failure_preservation": "Quality and decision gates are recorded with their actual values.",
        "artifacts_sha256": {path.relative_to(HERE).as_posix(): sha(path) for path in files_under(HERE)}, **checks})
    paths = [path for path in files_under(HERE) if path != HERE / "CONTENT_MANIFEST.json"]
    rows = [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in paths]
    dump(HERE / "CONTENT_MANIFEST.json", {"schema": "target-task-consumption-content-manifest-v1",
        "baseline_git": BASELINE, "scope": "Entire sole new namespace. Self and disposable namespace __pycache__ excluded. Raw runtime has no exclusions.",
        "file_count": len(rows), "bytes": sum(row["bytes"] for row in rows), "files": rows})
    print(json.dumps({"content_files": len(rows), "audit_sha256": sha(HERE / "FINAL_AUDIT.json"),
                      "manifest_sha256": sha(HERE / "CONTENT_MANIFEST.json"), "passed_checked_scope": True}))


def verify_git():
    manifest = read(HERE / "CONTENT_MANIFEST.json")
    pins(manifest["files"])
    actual_files = {path.relative_to(ROOT).as_posix() for path in files_under(HERE)}
    expected = {row["path"] for row in manifest["files"]} | {(HERE / "CONTENT_MANIFEST.json").relative_to(ROOT).as_posix()}
    require(len(manifest["files"]) == manifest["file_count"] and actual_files == expected, "exact namespace manifest closure")
    staged = {path.decode("utf-8") for path in git("diff", "--cached", "--name-only", "-z", BASELINE).split(b"\0") if path}
    require(staged == expected, "exact staged baseline diff closure")
    index = {}
    for row in git("ls-files", "--stage", "-z").split(b"\0"):
        if row:
            fields, path = row.split(b"\t", 1)
            mode, digest, stage = fields.split()
            require(stage == b"0", "unmerged Git index")
            index[path.decode("utf-8")] = digest.decode("ascii")
    for name in expected:
        require(index.get(name) == git_blob((ROOT / name).read_bytes()), "exact Git blob parity " + name)
    print(json.dumps({"manifest_and_staged_paths": len(expected), "exact_Git_blob_byte_parity": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-git", action="store_true")
    args = parser.parse_args()
    if args.verify_git:
        verify_git()
    else:
        seal()
