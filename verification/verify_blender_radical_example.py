"""Prepare a background Blender example and independently consume its public result."""

from argparse import ArgumentParser
from hashlib import sha256
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "artifacts/integration/preflight_001/native_002"
REGISTRATION = ROOT / "artifacts/integration/preflight_002/manifest.json"
DEPLOYMENTS = ROOT / "artifacts/integration/production_functional_001/deployments"
CASE_ID = "I-open-tip-0"
SEED = "20261105"
PACKAGES = ("before", "transition", "next")
sys.path.insert(0, str(ROOT))


def _identity(path, data=None):
    path = Path(path).resolve()
    data = path.read_bytes() if data is None else data
    return {"path": str(path), "bytes": len(data), "sha256": sha256(data).hexdigest()}


def _json(path):
    return json.loads(path.read_bytes())


def _write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, allow_nan=False, indent=2)
        stream.write("\n")


def _view_scores():
    manifest = _json(REGISTRATION)
    bb = manifest["method_probe"]["bb"]
    assert (ROOT / bb["archived_feedback_root"]).resolve() == HISTORICAL.resolve()
    assert manifest["deployments"][bb["deployment_process_index"]]["seed"] == SEED
    scores, sources = {}, {}
    for row in bb["archived_feedback"][CASE_ID]:
        record = HISTORICAL / row["archive_record"]
        image = HISTORICAL / CASE_ID / row["attachment_key"]
        raw = record.read_bytes()
        record_id, image_id = _identity(record, raw), _identity(image)
        assert record_id["sha256"] == row["archive_record_sha256"]
        assert image_id["sha256"] == row["png_sha256"]
        archived = json.loads(raw)
        evidence, score = archived["evidence"], archived["score"]
        assert evidence["candidate"] == row["canonical_index"]
        assert evidence["selected_rays"] == row["selected_probe_rays"]
        assert score["png_sha256"] == image_id["sha256"]
        assert score["passed"] is row["strict_verdict"]
        assert score["safe"] is row["safe"]
        assert type(score["pixel_success"]) is bool
        role = row["observation_id"]
        scores[role] = {"sha256": image_id["sha256"], "index": evidence["candidate"],
                        "pixel_pass": score["pixel_success"]}
        sources[role] = {"visual_record": record_id, "scored_png": image_id}
    assert list(scores) == ["before", "after"]
    return scores, sources


def make(out_dir):
    import bpy
    from verification.integration_fixtures import build_fixture, fixture_manifest
    from verification.test_integration_preflight import _materialize

    if not bpy.app.background:
        raise RuntimeError("Prepare the example in its own background Blender process")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=False)
    example_out = out_dir / "example-output"
    scores_path = out_dir / "view-scores.json"
    blend = out_dir / "fixture.blend"
    scores, score_sources = _view_scores()
    _write(scores_path, scores)
    deployment_report = DEPLOYMENTS / "summary.json"
    deployment = DEPLOYMENTS / f"{SEED}.npz"
    deployment_id = _identity(deployment)
    bound_deployment = _json(deployment_report)["seeds"][SEED]["deployment_file"]
    assert ROOT / bound_deployment["path"] == deployment
    assert deployment_id["sha256"] == bound_deployment["sha256"]
    assert deployment_id["bytes"] == bound_deployment["bytes"]

    spec = fixture_manifest()[0]
    assert spec.case_id == CASE_ID and spec.ordinal == 0
    case = build_fixture(spec)
    assert case.command.kind == "translate" and case.mode == "NATURAL"
    with _materialize(case) as (scene, objects):
        scene.name = CASE_ID
        scene.use_fake_user = True
        layer = scene.view_layers[0]
        scene_name, layer_name = scene.name, layer.name
        object_args = [f"{key}={obj.name}" for key, obj in objects.items()]
        window = bpy.context.window
        previous = window.scene if window is not None else None
        try:
            if window is not None:
                window.scene = scene
            with bpy.context.temp_override(scene=scene, view_layer=layer):
                layer.update()
                result = bpy.ops.wm.save_as_mainfile(filepath=str(blend), check_existing=True, copy=True)
                assert result == {"FINISHED"} and blend.is_file()
        finally:
            if window is not None:
                window.scene = previous

    example = ROOT / "examples/blender_radical_session.py"
    argv = [
        bpy.app.binary_path, "--background", "--factory-startup", "--disable-autoexec",
        "--threads", "1", "--python-exit-code", "1", "--python", str(example), "--",
        "--blend", str(blend), "--scene", scene_name, "--view-layer", layer_name,
    ]
    for binding in object_args:
        argv.extend(("--object", binding))
    schema = _json(HISTORICAL / "schema.json")["columns"]
    initial = dict(zip(schema["package"], _json(HISTORICAL / CASE_ID / "before.ao.json"), strict=True))
    observation = dict(zip(schema["observation"], initial["observations"][0], strict=True))
    generations = {}
    for row in observation["objects"]:
        fact = dict(zip(schema["object"], row, strict=True))
        key = initial["object_ids"][fact["object_index"]]
        generations[key] = fact["topology_generation"]
        argv.extend(("--generation", f"{key}={generations[key]}"))
    argv.extend((
        "--moving", case.target_ids[0], "--reference", case.target_ids[1],
        "--reference-frame", str(spec.frame_id), "--frame", str(spec.frame_id),
        "--goal-distance-m", str(case.goal_distance_m),
        "--goal-tolerance-m", str(case.goal_tolerance_m),
        "--mode", case.mode, "--view-arm", "L", "--predictor", "G",
        "--deployment", str(deployment), "--view-scores", str(scores_path),
        "--translate", *(str(value) for value in case.command.delta_world_m),
        "--out", str(example_out),
    ))
    _write(out_dir / "recipe.json", {
        "case": CASE_ID, "seed": SEED, "argv": sys.argv,
        "example_argv": argv, "example_cwd": str(ROOT), "example_out": str(example_out),
        "binding": {"scene": scene_name, "view_layer": layer_name, "objects": object_args,
                    "generations": generations,
                    "frame": spec.frame_id, "targets": list(case.target_ids),
                    "mode": case.mode, "view": "L", "predictor": "G"},
        "expected": {"translation_m": list(case.command.delta_world_m),
                     "before_gap_m": case.expected_before_m, "after_gap_m": case.expected_after_m,
                     "geometry_tolerance_m": case.goal_tolerance_m},
        "fixture_blend": _identity(blend), "deployment": deployment_id,
        "deployment_export_record": _identity(deployment_report), "example_source": _identity(example),
        "preflight_registration": _identity(REGISTRATION), "view_scores": _identity(scores_path),
        "archived_score_sources": score_sources,
        "historical_generation_sources": [_identity(HISTORICAL / "schema.json"),
                                          _identity(HISTORICAL / CASE_ID / "before.ao.json")],
        "historical_public_tree": str(HISTORICAL / CASE_ID),
        "historical_schema": str(HISTORICAL / "schema.json"),
    })


def _public_tree(consumer, root, schema_path):
    reader = consumer.Reader()
    schema = reader.json(schema_path, "public schema")
    packages = {}
    for phase in PACKAGES:
        path = root / f"{phase}.ao.json"
        packages[phase] = consumer.normalize(schema, reader.json(path, "public AO"), path, reader)
    return schema, packages, reader


def _roles(packages):
    before, transition, after_feedback = (packages[key] for key in PACKAGES)
    initial, = before["observations"]
    retained, final = transition["observations"]
    following, = after_feedback["observations"]
    observations = {"before": initial, "after": final, "next": following}
    identities = {row["observation_id"]: role for role, row in observations.items()}
    if len(identities) != 3:
        raise ValueError("Before, after and next must have distinct observation IDs")
    for row in observations.values():
        if row["image"]["path"] != f"{row['observation_id']}.png":
            raise ValueError("PNG attachment must be bound to its own observation ID")
    if retained != initial:
        raise ValueError("The transition changed the previously published before observation")
    if before["outcome"] is not None or after_feedback["outcome"] is not None:
        raise ValueError("Before and next must be standalone observations")
    outcome = transition["outcome"]
    if identities[outcome["before_observation_id"]] != "before" or identities[outcome["after_observation_id"]] != "after":
        raise ValueError("Transition Outcome is not bound to the retained before and actual after")
    return identities, observations, outcome


def _canonicalize(value, roles):
    """Replace role IDs and physical PNG paths without altering any fact."""
    if isinstance(value, list):
        return [_canonicalize(item, roles) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in ("observation_id", "before_observation_id", "after_observation_id"):
            result[key] = roles[item]
        elif key == "action_id":
            result[key] = "act"
        elif key == "path":
            attachment = Path(item).name
            result[key] = f"{roles[attachment.removesuffix('.png')]}.png"
        else:
            result[key] = _canonicalize(item, roles)
    return result


def check(recipe_path, report_path):
    import numpy
    import PIL
    from verification import ao_public_consumer as consumer

    recipe = _json(recipe_path)
    output = Path(recipe["example_out"])
    report = {
        "method": "Separate original AO public consumer normalize/Reader plus historical output comparison.",
        "recipe": _identity(recipe_path), "script": _identity(__file__),
        "consumer": _identity(consumer.__file__),
        "runtime": {"python": sys.version, "executable": _identity(sys.executable),
                    "numpy": numpy.__version__, "numpy_path": numpy.__file__,
                    "pillow": PIL.__version__, "pillow_path": PIL.__file__},
    }
    try:
        schema, actual, actual_reads = _public_tree(consumer, output, output / "schema.json")
        old_schema, old, old_reads = _public_tree(
            consumer, Path(recipe["historical_public_tree"]), Path(recipe["historical_schema"]))
        actual_ids, observed, outcome = _roles(actual)
        old_ids, _, old_outcome = _roles(old)
        before, after, following = (observed[phase] for phase in ("before", "after", "next"))
        tolerance = recipe["expected"]["geometry_tolerance_m"]
        expected_m = recipe["expected"]["translation_m"]
        translated = [right - left for left, right in zip(outcome["control_before"], outcome["control_after"],
                                                          strict=True)]
        after_state = _canonicalize(after["clearance"], {after["observation_id"]: "state"})
        next_state = _canonicalize(following["clearance"], {following["observation_id"]: "state"})
        roles_equal = {name: _canonicalize(actual[name], actual_ids) == _canonicalize(old[name], old_ids)
                       for name in PACKAGES}
        old_by_role = {role: name for name, role in old_ids.items()}
        image_hashes = {role: row["image"]["opened_png"]["sha256"] for role, row in observed.items()}
        old_image_hashes = {
            role: old_reads.files[str((Path(recipe["historical_public_tree"]) / f"{name}.png").resolve())]["sha256"]
            for role, name in old_by_role.items()
        }
        scores_path = Path(recipe["view_scores"]["path"])
        scores = _json(scores_path)
        report["checks"] = {
            "public_schema_matches": schema == old_schema,
            "fixture_frames": all(row["frame_id"] == recipe["binding"]["frame"] for row in observed.values()),
            "target_order_and_mode": all(row["image"]["mode"] == recipe["binding"]["mode"]
                                         and row["clearance"]["target_object_ids"] == recipe["binding"]["targets"]
                                         for row in observed.values()),
            "command_and_measured_translation": outcome["command"]["kind"] == "translate"
            and outcome["command"]["delta_world_m"] == expected_m
            and all(math.isclose(actual_m, wanted_m, rel_tol=0, abs_tol=tolerance)
                    for actual_m, wanted_m in zip(translated, expected_m, strict=True)),
            "gap_matches_fixture": all(math.isclose(row["clearance"]["distance_m"], expected, rel_tol=0,
                                                    abs_tol=tolerance)
                                       for row, expected in ((before, recipe["expected"]["before_gap_m"]),
                                                             (after, recipe["expected"]["after_gap_m"]))),
            "outcome_delta_matches_historical": outcome["measured_delta_m"] == old_outcome["measured_delta_m"],
            "next_reobserves_actual_after_clearance": after_state == next_state,
            "all_public_facts_match_historical_by_role": all(roles_equal.values()),
            "all_png_bytes_match_historical_by_role": image_hashes == old_image_hashes,
            "scored_inputs_bind_actual_pngs": _identity(scores_path) == recipe["view_scores"]
            and all(scores[role]["sha256"] == image_hashes[role] for role in ("before", "after")),
            "all_three_pngs_decoded": len(actual_reads.images) == 3,
        }
        report.update({"roles": actual_ids, "historical_roles": old_ids, "package_matches": roles_equal,
                       "actual_public_reads": list(actual_reads.files.values()),
                       "historical_public_reads": list(old_reads.files.values()),
                       "measured_delta_m": outcome["measured_delta_m"],
                       "predicted_delta_m": outcome["predicted_delta_m"],
                       "observed_gap_m": [row["clearance"]["distance_m"] for row in observed.values()],
                       "example_png_sha256": image_hashes, "historical_png_sha256": old_image_hashes,
                       "example_summary": _identity(output / "public-results.json")})
        report["passed"] = all(report["checks"].values())
    except (ValueError, OSError, KeyError, TypeError) as error:
        report.update({"passed": False, "error": f"{type(error).__name__}: {error}"})
    _write(report_path, report)
    return 0 if report["passed"] else 1


def main():
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    setup = commands.add_parser("make")
    setup.add_argument("--out-dir", type=Path, required=True)
    inspect = commands.add_parser("check")
    inspect.add_argument("--recipe", type=Path, required=True)
    inspect.add_argument("--report", type=Path, required=True)
    tail = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(tail)
    if args.operation == "make":
        make(args.out_dir)
        return 0
    return check(args.recipe, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
