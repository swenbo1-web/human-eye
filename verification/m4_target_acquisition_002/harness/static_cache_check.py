"""Pure mock and saved-wire checks, with zero live product or Blender calls."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from budget import save
from cache_extract_saved import extract


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def main():
    output = HERE.parent / "STATIC_CACHE_CHECK"
    output.mkdir(exist_ok=False)
    plan_path = HERE.parent / "fixtures/CACHE_CONTROL_PLAN.json"
    plan = load(plan_path)
    pins = [dict(row) for row in plan["harness_pins"]]
    pin_paths = [plan_path, Path("D:/he_m4_target_002/qualification/A_main/OWNER_BINDING.json"),
                 Path("D:/he_m4_target_002/assets_01/ASSETS.json")]
    for path in pin_paths:
        pins.append({"path": str(path), "sha256": digest(path)})
    save(output / "INPUTS.json", {"pins": pins})
    checks = []
    for pin in pins:
        assert digest(pin["path"]) == pin["sha256"]
    checks.append("all_input_pins_match_before_checks")
    for path in (HERE / "run_cache_control.py", HERE / "cache_owned_native.py", HERE / "cache_extract_saved.py"):
        ast.parse(path.read_text(encoding="utf-8"))
    checks.append("all_dedicated_sources_parse")
    patch = load(HERE.parent / "fixtures/CACHE_VERTEX_PATCH.json")
    assert len(patch["original_vertices"]) == len(patch["moved_vertices"]) == 289
    for before, after in zip(patch["original_vertices"], patch["moved_vertices"], strict=True):
        assert before[0] == 12 and after == [before[2] + 1.125, before[1] - .125, 2.09375]
        assert [struct.unpack("f", struct.pack("f", value))[0] for value in after] == after
    checks.append("all289_fixed_coordinates_equal_ideal_world_and_exact_binary32")
    spec = importlib.util.spec_from_file_location("_cache_native_mock_only", HERE / "cache_owned_native.py")
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    vertices = [SimpleNamespace(co=list(point)) for point in patch["original_vertices"]]
    polygons = [SimpleNamespace(vertices=list(face), material_index=0, use_smooth=False)
                for face in patch["source_triangles"]]
    mesh = SimpleNamespace(vertices=vertices, polygons=polygons, edges=[], materials=[], update=lambda: None)
    target = SimpleNamespace(name="M4_Far_11", type="MESH", parent=None,
                             matrix_world=copy.deepcopy(patch["matrix_world"]), data=mesh,
                             hide_render=False, hide_viewport=False, hide_get=lambda: False)
    sentinel = SimpleNamespace(name="UntouchedSentinel", type="EMPTY", parent=None,
                               matrix_world=copy.deepcopy(patch["matrix_world"]), data=SimpleNamespace(),
                               hide_render=False, hide_viewport=False, hide_get=lambda: False)
    bpy = SimpleNamespace(data=SimpleNamespace(objects=[target, sentinel]),
                          context=SimpleNamespace(view_layer=SimpleNamespace(update=lambda: None),
                              scene=SimpleNamespace(unit_settings=SimpleNamespace(scale_length=1),
                                                    frame_current=1, frame_subframe=0)))
    initial = native._scene_fingerprint(bpy)
    moved = native._apply_far11_fixture_vertices(bpy, 1)
    assert moved["vertices_written"] == 289 and moved["before_fingerprint"] == initial
    assert [list(vertex.co) for vertex in vertices] == patch["moved_vertices"]
    assert moved["after_fingerprint"] != initial
    checks.append("mock_move_writes_exact_vertices_and_checks_full_scene")
    restored = native._apply_far11_fixture_vertices(bpy, 2)
    assert restored["vertices_written"] == 289 and restored["after_fingerprint"] == initial
    assert native._scene_fingerprint(bpy) == initial
    checks.append("mock_restore_recovers_complete_initial_fingerprint")
    before = native._scene_fingerprint(bpy)
    try:
        native._apply_far11_fixture_vertices(bpy, 2)
    except ValueError as error:
        assert str(error) == "visual004_native_cache_fixture_before_vertices"
    else:
        raise AssertionError("restore_from_wrong_state_must_reject")
    assert native._scene_fingerprint(bpy) == before
    checks.append("wrong_mock_state_rejected_before_any_change")
    old_slot = Path("D:/he_m4_target_002/qualification/A_main")
    owner = load(old_slot / "OWNER_BINDING.json")
    asset = next(row for row in load("D:/he_m4_target_002/assets_01/ASSETS.json")["inputs"] if row["name"] == "main")
    binding = load(HERE.parent / "A_RUN_BINDING.json")
    baseline = output / "saved_A_baseline"
    baseline.mkdir()
    extract(baseline, asset, binding, owner["source_proof"]["actual_runtime_identity"],
            wire_root=old_slot / "native/WIRE", sequence_range=(1, 2), phase="static_saved_baseline", setup_receipts=[])
    replay = load(baseline / "OWNER_BINDING.json")
    assert replay["main_capture_count"] == 1 and replay["post_main_readback_count"] == 1
    for actual, expected in zip(replay["captures"], owner["captures"], strict=True):
        assert load(actual["capture"]) == load(expected["capture"])
        assert actual["mapping"] == expected["mapping"]
    checks.append("saved_A_wire_both_capture_values_and_mappings_match_existing_acceptance")
    readback = output / "saved_A_readback_only"
    readback.mkdir()
    extract(readback, asset, binding, owner["source_proof"]["actual_runtime_identity"],
            wire_root=old_slot / "native/WIRE", sequence_range=(2, 2), phase="static_saved_readback", setup_receipts=[])
    replay = load(readback / "OWNER_BINDING.json")
    assert replay["main_capture_count"] == 0 and replay["post_main_readback_count"] == 1
    assert load(replay["captures"][0]["capture"]) == load(owner["captures"][1]["capture"])
    checks.append("saved_phase_range_reuses_prior_resources_without_emitting_prior_main")
    for pin in pins:
        assert digest(pin["path"]) == pin["sha256"]
    checks.append("all_input_pins_unchanged_after_checks")
    result = {"passed": True, "checks": checks, "pins": pins, "actual_Blender_starts": 0,
              "actual_product_calls": 0, "actual_rasters": 0, "models": 0,
              "scope": "pure Python mock setter contract and replay of previously saved A bytes only",
              "author_association": "this checker and the dedicated fixture/harness share an author; live acceptance requires independent review"}
    save(output / "RESULT.json", result)
    print(json.dumps({"passed": True, "checks": len(checks), "result": str(output / "RESULT.json"),
                      "sha256": digest(output / "RESULT.json")}))


if __name__ == "__main__":
    main()
