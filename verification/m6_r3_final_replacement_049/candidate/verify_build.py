"""Verify the fixed final install independently of its builder."""
import ast
from hashlib import file_digest, sha256
import json
from pathlib import Path
import sys
from zipfile import ZipFile

PROX = "human_eye_plugin/surface_proximity.py"
GEOM = "human_eye_plugin/surface_geometry.py"
OLD_PROX = "human_eye_plugin/_surface_proximity_032.py"
OLD_GEOM = "human_eye_plugin/_surface_geometry_032.py"


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open("rb") as stream:
        return file_digest(stream,"sha256").hexdigest()


def from_pin(pin):
    path = Path(pin["path"])
    assert path.stat().st_size == pin["bytes"] and sha(path) == pin["sha256"], pin
    return path


def function_nodes(source):
    return {node.name:ast.dump(node,include_attributes=False)
            for node in ast.parse(source).body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}


def verify(pins_path):
    pins = read(pins_path)
    f = Path(pins["site"])
    wheel = from_pin(pins["wheel"])
    binding = read(from_pin(pins["binding"]))
    assert pins["source_manifest"] == binding["source_files"] and pins["identity"]==binding["identity"]
    with ZipFile(wheel) as original:
        for row in binding["source_files"]:
            assert sha(f/row["path"])==sha256(original.read(row["path"])).hexdigest()==row["sha256"]
    a, c = [Path(read(from_pin(pins["baseline_"+arm]))["site_packages"]) for arm in "AC"]
    assert (f/OLD_PROX).read_bytes().replace(b"from ._surface_geometry_032 import",b"from .surface_geometry import")==(
        a/PROX).read_bytes()
    assert (f/OLD_GEOM).read_bytes().replace(b"from . import _surface_proximity_032 as exact",
                                           b"from . import surface_proximity as exact")==(
        a/GEOM).read_bytes()
    changed = {row["path"] for row in binding["source_files"]
               if not (c/row["path"]).is_file() or sha(c/row["path"])!=row["sha256"]}
    assert changed=={PROX,GEOM,OLD_PROX,OLD_GEOM}
    allowed = {
        PROX: {"_use_032_surface","measure_surface_proximity","measure_spatial_relation"},
        GEOM: {"classify_closed_solids"},
    }
    for name, expected in allowed.items():
        previous = function_nodes((c/name).read_bytes())
        after = function_nodes((f/name).read_bytes())
        assert {node for node in previous.keys()|after.keys() if previous.get(node)!=after.get(node)}==expected
    assert sha(f/"human_eye_hook.py")==sha(c/"human_eye_hook.py")==sha(a/"human_eye_hook.py")
    for name in ("launcher","admin","startup","patch","design","builder"):
        from_pin(pins[name])
    added = sum((f/path).stat().st_size for path in (OLD_PROX,OLD_GEOM))
    return {"status":"pass","verified_source_files":len(binding["source_files"]),
            "changed_or_added":sorted(changed),"changed_existing_functions":{k:sorted(v) for k,v in allowed.items()},
            "032_internal_copy_bytes":added,"032_inlining":"exact installed original bytes after reversing two relative imports",
            "wheel":pins["wheel"],"hook_equal":True,"public_limits_modified":False,"geometry_runs":0}


if __name__=="__main__":
    summary = verify(Path(sys.argv[1]))
    with Path(sys.argv[2]).open("x",encoding="utf-8") as stream:
        json.dump(summary,stream,indent=2)
        stream.write("\n")
    print(summary)

