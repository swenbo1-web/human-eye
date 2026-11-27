"""Close the read-only 048 archive with exact custodial copies and an index."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-048-R3-WITNESS-PARITY/closed_archive")


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest)


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return pin(path)


def exact_copy(ref, target):
    if pin(ref["path"]) != ref:
        raise ValueError("source_ref_changed:" + ref["path"])
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(Path(ref["path"]).read_bytes())
    copied = pin(target)
    if (copied["bytes"], copied["sha256"]) != (ref["bytes"], ref["sha256"]):
        raise ValueError("custody_copy_changed")
    return dict(original=ref, copy=copied)


def main():
    frozen = read(RAW / "ARCHIVE_FREEZE.json")
    inputs = read(RAW / "INPUTS.json")
    result = read(RAW / "RESULTS.json")
    if result["status"] != "pass" or pin(frozen["script"]["path"]) != frozen["script"]:
        raise ValueError("audit_not_held")
    for ref in (inputs["geometry"], inputs["truth"], *inputs["ordinary_public"].values()):
        if pin(ref["path"]) != ref:
            raise ValueError("bound_output_changed")
    save(RAW / "FINALIZE_FREEZE.json", dict(
        schema="m6-048-closed-archive-finalize-freeze-v1",
        frozen_utc=datetime.now(timezone.utc).isoformat(),
        source=pin(Path(__file__)), source_freeze=pin(RAW / "ARCHIVE_FREEZE.json"),
        inputs=pin(RAW / "INPUTS.json"), results=pin(RAW / "RESULTS.json"),
        action="Exact custodial copying and report/index only; no product imports or numerical search"))
    custody = {}
    for key, ref in frozen["old_refs"].items():
        target = RAW / "custody" / key
        if not target.resolve().is_relative_to(RAW.resolve()):
            raise ValueError("invalid_custody_key")
        custody[key] = exact_copy(ref, target)
    custody["audit_source"] = exact_copy(frozen["script"], RAW / "source" / "archive.py")
    custody["finalize_source"] = exact_copy(pin(Path(__file__)), RAW / "source" / "finalize.py")
    custody_ref = save(RAW / "CUSTODY.json", dict(
        schema="m6-048-closed-archive-custody-v1", status="pass", entries=custody,
        originals=inputs["originals"],
        interpretation="Each copy is byte-identical to its frozen original. Original absolute provenance remains intact in bound outputs."))
    public = {arm: read(inputs["ordinary_public"][arm]["path"]) for arm in ("A", "C")}
    summary = dict(
        schema="m6-048-closed-archive-summary-v1", status="pass",
        geometry=inputs["geometry"], truth=inputs["truth"], inputs=pin(RAW / "INPUTS.json"),
        results=pin(RAW / "RESULTS.json"), custody=custody_ref,
        pair=inputs["pair"], vertex_counts=[48, 8], triangle_counts=[96, 12],
        primitive_pair_domain=1152, original_independent_exact_pairs=1152,
        original_minimizing_face_pairs=14, canonical_native_face_pair=[90, 2],
        canonical_native_face_vertices=[[23, 47, 36], [4, 5, 6]],
        distance_m=0.010000049869218474, relation="separated",
        archived_ordinary={arm: dict(
            public=inputs["ordinary_public"][arm],
            measured_path=public[arm]["path"],
            surface_work=public[arm]["work"]["surface_work"],
            closed_solid_work=public[arm]["work"]["closed_solid_work"],
            product_pid=public[arm]["original_product_pid"],
            GUI_pid=public[arm]["original_GUI_pid"],
            business_ns=public[arm]["original_descriptive_business_ns"])
            for arm in ("A", "C")},
        public_surface_and_relation_equal=True,
        native_pair_origin="Existing independent 044 exact oracle and separate matched shared-preparation queue diagnostic; absent from ordinary public reply",
        regular_distance_status="Not measured in this archive task. Parent may run the same ordered world arrays through the original regular kernel.",
        missing_public_fields=result["missing_public_fields"],
        new_calls=result["new_calls"], archive_mismatches=[])
    summary_ref = save(RAW / "SUMMARY.json", summary)
    save(HERE / "SUMMARY.json", summary)
    readme = f"""# 048 closed-family archive\n\nThis archive binds the fixed Object_01 → Object_02 source from 044: 48/8 original vertices, 96/12 original triangles, and all 1,152 primitive pairs in the old independent rational oracle. No kernel, Blender, installation, timing or new asset generation ran in this task.\n\nUse `GEOMETRY.json` top-level `left` and `right`. Each contains `name`, `vertices_world`, `faces`, `vertices_local`, `matrix_world`, `source_triangle_rows`, `triangle_polygons` and byte hashes. World coordinates are already the actual captured binary64 metres; do not transform them again. Vertex and face order are preserved. Actual native/evaluated arrays, old oracle arrays and original author arrays agree; the original before/after full-scene captures agree.\n\n`CANONICAL_TRUTH.json` binds the unchanged old exact distance square, the exact canonical point pair, 14 minimizing face pairs, and canonical native pair `[90, 2]` (source vertex rows `[[23,47,36],[4,5,6]]`). Distance is `0.010000049869218474` metres. The 14 face-pair ties alone do not establish point uniqueness or a general witness feature rule.\n\nThe old real ordinary A/C query requested `closed_solid_relation` then `surface_proximity`; both facts are measured, relation is `separated`, and public surface values, rounded point pair and direction agree. The surface phase used shared preparation and trees from the relation phase. Its charged work is A 1,565 / C 921 and narrow calls A 25 / C 9. These are preserved historical audit counts, not a new timing comparison.\n\nThe public reply omits the exact squared distance, rational point pair, canonical native face pair, and internal witness descriptor. The old separate matched shared-tree diagnostic returned `[90,2]`; it is explicitly not a public field or a regular surface-only measurement. No regular surface-only run is supplied by this archive.\n\n`INPUTS.json` is the machine entry point; `SUMMARY.json` records path and field scope. `ordinary/{{A,C}}/004.TX.bin` and `004.RX.bin` are original wire bytes, with decoded original public facts in `PUBLIC.json`. `custody/` stores exact copies of every frozen source/audit/diagnostic reference, and `originals/` stores the three original inputs. `CUSTODY.json` maps every copy back to its old path, bytes and SHA. `INDEX.json` seals this scope; original absolute provenance is retained in all bound outputs.\n\nGeometry SHA: `{inputs['geometry']['sha256']}`. Truth SHA: `{inputs['truth']['sha256']}`. Summary SHA: `{summary_ref['sha256']}`.\n\nThe audit source is `archive.py` (`freeze` then `run`); `finalize.py` performs only custodial copying and reporting. Both use exclusive-create outputs and are preserved under raw `source/`. All old references were hashed before audit; no old archive was modified.\n"""
    for path in (HERE / "README.md", RAW / "README.md"):
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(readme)
    files = [pin(path) for path in sorted(RAW.rglob("*")) if path.is_file()]
    stage_files = [pin(path) for path in sorted(HERE.iterdir()) if path.is_file()]
    index = dict(schema="m6-048-closed-archive-index-v1", status="closed",
        created_utc=datetime.now(timezone.utc).isoformat(), raw_root=str(RAW), stage_root=str(HERE),
        raw_files=files, stage_files=stage_files,
        index_self_excluded=True, source_freeze=pin(RAW / "ARCHIVE_FREEZE.json"),
        geometry=inputs["geometry"], truth=inputs["truth"], results=pin(RAW / "RESULTS.json"),
        source_and_output_mutations_after_index="none intended", new_calls=result["new_calls"])
    print(save(RAW / "INDEX.json", index))
    print(save(HERE / "INDEX.json", index))


if __name__ == "__main__":
    main()
