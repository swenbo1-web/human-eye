"""Build the final single wheel from installed, hash-checked 032 and corrected R3."""
from __future__ import annotations
import ast
import difflib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT")
OUT = RAW/"candidate"
PREVIOUS = RAW.parent/"M6-047-R3-COVERAGE-DOMAIN/FREEZE.json"
SOURCE_C = RAW.parent/"M6-043-R3-REGION-ATTRIBUTION/candidate/source"
BASE = "6c93f2375d1073b33e721a168f1fcf610ac6dbdc"
EDITION = "9.7.2+k049final"
PROX = "human_eye_plugin/surface_proximity.py"
GEOM = "human_eye_plugin/surface_geometry.py"
OLD_PROX = "human_eye_plugin/_surface_proximity_032.py"
OLD_GEOM = "human_eye_plugin/_surface_geometry_032.py"

spec = importlib.util.spec_from_file_location("installed_recipe_043",
    HERE.parents[1]/"m6_r3_region_attribution_043/candidate/build.py")
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)
sha, ref, put, save, replace = recipe.sha, recipe.artifact, recipe.put, recipe.save, recipe.replace_exact

SELECTOR = '''def _use_032_surface(left, right):
    """Select before changing preparation or the original per-pair work ledger."""
    try:
        n, m = len(left.faces), len(right.faces)
    except (AttributeError, TypeError):
        return True
    product = n * m
    if not product or n + m > MAX_FACES or product > MAX_NARROW_PHASE_PAIRS:
        return True
    # Conservative R3 work bound for preparation, traversal, settled credit
    # spend, and source checks at publication.
    return n*n + m*m + 8*(n + m) + 124*product + 4 > MAX_WORK_UNITS


'''
DISTANCE = '''    if _use_032_surface(left, right):
        from ._surface_proximity_032 import measure_surface_proximity as original
        measured = original(
            left, right, checkpoint, diagnostics=diagnostics,
            retain_exact_rank=retain_exact_rank, retain_witness_triangles=retain_witness_triangles,
            _prepared_pair=_prepared_pair, _boundary_contact=_boundary_contact,
            _prepared_trees=_prepared_trees, _prepared_holder=_prepared_holder)
        measured['work']['solver_path'] = '032'
        return measured
'''
SPATIAL = '''    if _use_032_surface(left, right):
        from ._surface_proximity_032 import measure_spatial_relation as original
        measured = original(left, right, checkpoint, diagnostics=diagnostics,
                            retain_exact_rank=retain_exact_rank, prepared_holder=prepared_holder)
        measured['surface']['work']['solver_path'] = '032'
        return measured
'''
CLOSED = '''    if exact._use_032_surface(left, right):
        from ._surface_geometry_032 import classify_closed_solids as original
        measured = original(left, right, checkpoint, diagnostics=diagnostics,
                            prepared_pair=prepared_pair, prepared_holder=prepared_holder,
                            prepared_trees=prepared_trees)
        measured['work']['solver_path'] = '032'
        return measured
    budget=_ClosedWork(checkpoint,diagnostics,exact)
    budget.counts['solver_path'] = 'r3'
'''


def read(path):
    return json.loads(Path(path).read_bytes())


def verified_arm(row):
    binding = Path(row["binding"]["path"])
    assert ref(binding) == row["binding"]
    params = read(binding)
    assert len(params["source_files"]) == 143 and params["identity"] == row["identity"]
    site = Path(params["site_packages"])
    sources = {entry["path"]: (site/entry["path"]).read_bytes() for entry in params["source_files"]}
    assert {path: sha(blob) for path,blob in sources.items()} == {
        entry["path"]: entry["sha256"] for entry in params["source_files"]}
    return binding, params, sources


def compile_changes(a, c):
    for name in (PROX, GEOM):
        expected = subprocess.check_output(["git","show",f"{BASE}:{name}"],cwd=HERE)
        assert expected.replace(b"\r\n",b"\n") == a[name].replace(b"\r\n",b"\n")
    prox = replace(c[PROX], "def measure_surface_proximity(", SELECTOR+"def measure_surface_proximity(", 1)
    marker = "        raise ValueError(f'unsupported projection_mode: {mode!r}')\n"
    admission = "    checkpoint('surface_proximity_admission')"
    prox = replace(prox, marker+admission, marker+DISTANCE+admission, 1)
    marker = "    budget = _Work(checkpoint, diagnostics)\n    budget.counts['witness_projection_mode']"
    prox = replace(prox, marker, "    budget = _Work(checkpoint, diagnostics)\n"
                   "    budget.counts['solver_path'] = 'r3'\n    budget.counts['witness_projection_mode']", 1)
    marker = '    """Prove sufficient support separation, or run the original classifier once."""\n'
    prox = replace(prox, marker, marker+SPATIAL, 1)
    geom = replace(c[GEOM], "    budget=_ClosedWork(checkpoint,diagnostics,exact)\n", CLOSED, 1)
    changes = {
        PROX: prox, GEOM: geom,
        OLD_PROX: replace(a[PROX], "from .surface_geometry import", "from ._surface_geometry_032 import", 2),
        OLD_GEOM: replace(a[GEOM], "from . import surface_proximity as exact",
                          "from . import _surface_proximity_032 as exact", 1),
    }
    assert OLD_PROX not in c and OLD_GEOM not in c
    for name, data in changes.items():
        ast.parse(data, filename=name)
    return changes


def main():
    frozen = read(PREVIOUS)["runtime"]
    a_file, a_manifest, a = verified_arm(frozen["A"])
    c_file, c_manifest, c = verified_arm(frozen["C"])
    changes = compile_changes(a,c)
    source = OUT/"source"
    combined = c | changes
    assert len(combined) == 145
    sources = [dict(path=name,sha256=sha(data)) for name,data in sorted(combined.items())]
    python = c_manifest["dependency_python"]
    assert python == a_manifest["dependency_python"]
    assert a["human_eye_hook.py"] == c["human_eye_hook.py"] == combined["human_eye_hook.py"]
    assert not (OUT/"PINS.json").exists()
    for name, data in combined.items():
        put(source/name, data)
    extras = {name: ref(SOURCE_C/name) for name in recipe.EXTRAS}
    for name in extras:
        put(source/name,(SOURCE_C/name).read_bytes())

    patch = b"".join("".join(difflib.unified_diff(c.get(name,b"").decode().splitlines(True),
        after.decode().splitlines(True),fromfile="a/"+name if name in c else "/dev/null",
        tofile="b/"+name)).encode() for name,after in changes.items())
    put(OUT/"F.patch",patch)
    put(HERE/"F.patch",patch)
    output = OUT/"build"
    build = subprocess.run([python,"-I","-B",str(source/recipe.BUILD),
                            "--output",str(output),"--version",EDITION],
                           cwd=source,capture_output=True,timeout=90)
    put(OUT/"BUILDER.stdout",build.stdout)
    put(OUT/"BUILDER.stderr",build.stderr)
    build.check_returncode()
    record = read(output/"BUILD.json")
    runtime = record["runtime_identity"]
    assert record["deterministic_rebuild"] and runtime["source_files"] == sources
    wheel_row, = [x for x in record["artifacts"] if x["file"].endswith(".whl")]
    wheel = output/wheel_row["file"]
    assert ref(wheel)["sha256"] == wheel_row["sha256"]
    release = (OUT/".human-eye/releases"/EDITION).resolve()
    site = release/"site-packages"
    with ZipFile(wheel) as package:
        assert len(package.namelist()) == len(set(package.namelist()))
        for name in package.namelist():
            part = PurePosixPath(name)
            assert not part.is_absolute() and ".." not in part.parts and ":" not in name and "\\" not in name
            put(site/Path(*part.parts), package.read(name))
    assert all(sha((site/x["path"]).read_bytes()) == x["sha256"] for x in sources)

    before, admin = c_file.parent, release/"admin"
    launcher = (before/"target_runtime_entry.py").read_bytes()
    manager = (before/"installed_release.py").read_bytes()
    assert sha(launcher) == c_manifest["launcher_sha256"] and sha(manager) == c_manifest["admin_sha256"]
    launcher = replace(launcher,c_manifest["identity"]["distribution_version"],EDITION,2)
    digest = runtime["source_sha256"]
    launcher = replace(launcher,c_manifest["identity"]["source_sha256"],digest,3)
    launcher = replace(launcher, "len(manifest) != 143", f"len(manifest) != {len(sources)}", 1)
    launcher = replace(launcher, "143-file core", f"{len(sources)}-file core", 1)
    manager = replace(manager,c_manifest["launcher_sha256"],sha(launcher),1)
    launcher_path = admin/"target_runtime_entry.py"
    put(launcher_path,launcher)
    put(admin/"installed_release.py",manager)
    identity = {k:runtime[k] for k in c_manifest["identity"] if k!="distribution_version"}
    identity["distribution_version"] = EDITION
    binding = admin/"RUNTIME_BINDING.json"
    save(binding, dict(c_manifest,target_release=str(release),site_packages=str(site),identity=identity,
                      launcher_sha256=sha(launcher),admin_sha256=sha(manager),source_files=sources))
    command = [python,"-I","-B",str(launcher_path)]
    startup = subprocess.run(command+["identity"],cwd=OUT,capture_output=True,timeout=30)
    put(OUT/"STARTUP.stdout.json",startup.stdout)
    put(OUT/"STARTUP.stderr",startup.stderr)
    startup.check_returncode()
    readback = read(OUT/"STARTUP.stdout.json")
    assert not startup.stderr and all(readback["runtime_identity"][k]==v for k,v in identity.items())
    assert readback["launcher"]["binding_sha256"] == ref(binding)["sha256"]
    assert verified_arm(frozen["A"])[2] == a and verified_arm(frozen["C"])[2] == c
    pins = dict(schema="m6-049-one-final-candidate",status="installed_identity_verified",
                source_sha256=digest,source_count=len(sources),source_manifest=sources,version=EDITION,
                identity=identity,site=str(site),source=str(source),release=str(release),
                dependency_python=python,binding=ref(binding),launcher=ref(launcher_path),
                admin=ref(admin/"installed_release.py"),wheel=ref(wheel),build=ref(output/"BUILD.json"),
                startup=ref(OUT/"STARTUP.stdout.json"),patch=ref(OUT/"F.patch"),
                design=ref(HERE/"DESIGN.md"),builder=ref(Path(__file__)),baseline_A=ref(a_file),
                baseline_C=ref(c_file),packaging_sources=extras,changed_sources=sorted(changes),
                arm=dict(source_sha256=digest,version=EDITION,site_packages=str(site),role="049 final F",
                         command_prefix=command,binding=ref(binding)))
    save(OUT/"PINS.json",pins)
    save(HERE/"PINS.json",pins)
    print(ref(OUT/"PINS.json"))


if __name__=="__main__":
    main()

