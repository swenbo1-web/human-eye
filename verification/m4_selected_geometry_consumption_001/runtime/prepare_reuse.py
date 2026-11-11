"""Create four bounded formal-runtime copies without launching a backend."""

import ast
import difflib
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
OLD = ROOT / "verification/m4_local_relation_consumption_001"
CYCLE = "M4-SELECTED-GEOMETRY-CONSUMPTION-001"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)


def replace_assignment(text, name, replacement):
    node = next(node for node in ast.parse(text).body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
    source = ast.get_source_segment(text, node)
    assert text.count(source) == 1
    return text.replace(source, replacement, 1)


def main():
    originals = {
        "actor.py": OLD / "runtime/actor.py",
        "consumer_transport.py": OLD / "runtime/consumer_transport.py",
        "driver.py": OLD / "runtime/driver.py",
        "pack_quality.py": OLD / "quality_handoff/pack_quality.py",
    }
    reused = {}
    for name, source in originals.items():
        original = source.read_bytes()
        text = original.decode("utf8")
        if name == "driver.py":
            text = replace_assignment(text, "SOURCE_BY_PROFILE", "SOURCE_BY_PROFILE={\n    'P':'53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732',\n    'G':'4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c'}")
            text = replace_assignment(text, "COMMIT_BY_PROFILE", "COMMIT_BY_PROFILE={\n    'P':'e077fce38b5951efff8166b3b688d05ffa2ebf04',\n    'G':'00b13060a3cbe709b38f6e98ce04a6e5c3dabfb4'}")
            text = text.replace("'P0'", "'P'").replace("'P1'", "'G'")
            text = text.replace("'lrc'+", "'sgc'+")
        elif name == "pack_quality.py":
            text = text.replace("'P0'", "'P'").replace("'P1'", "'G'")
        if name in ("driver.py", "pack_quality.py"):
            text = text.replace("M4-LOCAL-RELATION-CONSUMPTION-001", CYCLE)
        current = original if name in ("actor.py", "consumer_transport.py") else text.encode("utf8")
        ast.parse(current)
        put(HERE / name, current)
        difference = "".join(difflib.unified_diff(original.decode().splitlines(keepends=True), current.decode().splitlines(keepends=True),
            fromfile=str(source.relative_to(ROOT)), tofile="runtime/" + name))
        if difference:
            put(HERE / (name + ".diff"), difference.encode())
        reused[name] = {"source": str(source.relative_to(ROOT)), "source_sha256": sha(original),
                        "current_sha256": sha(current), "byte_identical": original == current}
        assert source.read_bytes() == original
    driver_old = ast.parse(originals["driver.py"].read_bytes())
    driver_new = ast.parse((HERE / "driver.py").read_bytes())
    unchanged = ("prepare", "finish", "snapshot_binding", "run_models")
    for name in unchanged:
        old = next(node for node in driver_old.body if isinstance(node, ast.FunctionDef) and node.name == name)
        new = next(node for node in driver_new.body if isinstance(node, ast.FunctionDef) and node.name == name)
        assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False)
    backend = ROOT / "verification/native_plugin_complex_003/reused/accepted_native.py"
    backend_raw = backend.read_bytes()
    actor = (HERE / "actor.py").read_bytes()
    assert b"sys.setprofile" not in backend_raw and b"qa_profile_schedule" not in backend_raw
    assert b"qa_instrumentation" not in actor and b"qa_profile_schedule" not in actor
    cli = Path("C:/Users/Administrator/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe")
    assert sha(cli.read_bytes()) == "01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6"
    receipt = {"cycle_id": CYCLE, "files": reused, "unchanged_driver_function_AST": list(unchanged),
        "CLI": {"path": str(cli), "sha256": sha(cli.read_bytes())},
        "formal_backend": {"path": str(backend.relative_to(ROOT)), "sha256": sha(backend_raw),
            "profile_schedule_parameter": False, "QA_profiler_installation": False,
            "source": "original accepted native 003 implementation"},
        "external_groups": ["N", "P", "G"], "internal_actor_transport_groups": ["N", "P"],
        "fresh_cell_ids": ["sgc" + str(index).zfill(2) for index in range(1, 10)],
        "formal_quality_packager": "runtime/pack_quality.py",
        "packager_default_output_parent": "runtime",
        "model_consumers": 0, "Blender_sessions": 0, "product_processes": 0,
        "preparer_source_sha256": sha(Path(__file__).read_bytes())}
    put(HERE / "REUSE_BINDINGS.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"cycle_id": CYCLE, "prepared_files": 4, "consumers": 0}))


if __name__ == "__main__":
    main()
