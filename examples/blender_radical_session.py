"""Run a public Blender session from an explicit .blend and consume its AO and PNG."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import struct
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from human_eye_fast import (
    BlenderRadicalSession, CaptureChange, Goal, MeshChange, ObservationRequest, PreparedAction,
    ReferenceFrame, SetShapeKey, Translate, ViewFeedback, load_cf_deployment,
)
from human_eye_fast.blender_resident_bridge import BlenderResidentBridge
from human_eye_fast.fast_affordance_out import public_schema


def read_public_package(schema, ao_bytes, attachments):
    """Read a he-ao/1 package without a live session, model, mesh or scene."""
    columns = schema["columns"]

    def unpack(kind, values):
        return dict(zip(columns[kind], values, strict=True))

    package = unpack("package", json.loads(ao_bytes))
    if package["version"] != schema["versions"]["candidate"] or package["length_unit"] != "m":
        raise ValueError("Expected the public meter-space AO format")
    observations = []
    seen = set()
    for row in package["observations"]:
        observation = unpack("observation", row)
        image = observation["image"]
        if image is not None:
            image = unpack("image", image)
            key = image["path"]
            if key != f"{observation['observation_id']}.png":
                raise ValueError("Image key does not match its observation")
            png = attachments[key]
            if (png[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
                    or struct.unpack(">II", png[16:24]) != (image["width_px"], image["height_px"])):
                raise ValueError("PNG header does not match the public image dimensions")
            image = {**image, "sha256": sha256(png).hexdigest()}
            seen.add(key)
        observations.append({
            "observation_id": observation["observation_id"], "frame_id": observation["frame_id"],
            "clearance": unpack("clearance", observation["clearance"]), "image": image,
        })
    if seen != attachments.keys():
        raise ValueError("Unexpected PNG attachment")
    outcome = package["outcome"]
    return {"observations": observations, "outcome": None if outcome is None else unpack("outcome", outcome)}


def submit_scored_view(session, result, public_answer, scores):
    ticket = result.view_ticket
    if ticket is None or scores is None:
        return
    image = next(row["image"] for row in public_answer["observations"]
                 if row["observation_id"] == result.observation_id)
    score = scores[result.observation_id]
    if (score["sha256"] != image["sha256"] or score["index"] != ticket.index
            or type(score["pixel_pass"]) is not bool):
        raise ValueError("The external pixel verdict does not bind the actual PNG and direction")
    session.view_feedback(ticket, ViewFeedback(result.observation_id, image["path"], ticket.index,
                                               score["pixel_pass"]))


def capture_reference(bpy, scene, view_layer, moving_id, moving, frame, generation):
    scene.frame_set(frame)
    bridge = BlenderResidentBridge()
    with bpy.context.temp_override(scene=scene, view_layer=view_layer):
        mesh = bridge.capture(moving_id, moving, bpy.context.evaluated_depsgraph_get(),
                              scene.unit_settings.scale_length)
        reference = ReferenceFrame(frame, generation, mesh.world_m)
    bridge.clear()
    return reference


def run(args):
    import bpy

    args.out.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve(strict=True)), load_ui=False, use_scripts=False)
    scene = bpy.data.scenes[args.scene]
    layer = scene.view_layers[args.view_layer]
    pairs = [item.split("=", 1) for item in args.object]
    objects = {key: scene.objects[name] for key, name in pairs}
    if len(objects) != len(pairs):
        raise ValueError("Provide distinct object IDs")
    generations = {key: index for index, key in enumerate(objects, start=1)}
    if args.generation is not None:
        declared = [item.split("=", 1) for item in args.generation]
        generations = {key: int(value) for key, value in declared}
        if len(generations) != len(declared) or generations.keys() != objects.keys():
            raise ValueError("Provide one topology generation for each object ID")
    goal = Goal(args.moving, args.reference, args.goal_distance_m, args.goal_tolerance_m)
    reference = capture_reference(bpy, scene, layer, args.moving, objects[args.moving],
                                  args.reference_frame, generations[args.moving])
    scene.frame_set(args.frame)
    deployment = None if args.deployment is None else load_cf_deployment(args.deployment)
    scores = None if args.view_scores is None else json.loads(args.view_scores.read_bytes())
    command = (Translate(tuple(args.translate)) if args.translate is not None else
               SetShapeKey(args.shape_key[0], float(args.shape_key[1])))
    mode = None if args.mode == "NONE" else args.mode
    schema = public_schema()
    changed = MeshChange.VERTICES | MeshChange.TRANSFORM | MeshChange.UNITS
    changes = {key: CaptureChange(changed) for key in objects}
    outputs = {}
    with BlenderRadicalSession(scene, layer, objects, goal, generations, reference=reference,
                               deployment=deployment) as session:
        if isinstance(command, SetShapeKey) and args.predictor != "NONE":
            session.prepare_relative_basis(command.key_name)
        before = session.observe(ObservationRequest("before", mode, args.view_arm), changes=changes)
        before_answer = read_public_package(schema, before.ao_bytes, before.attachments)
        outputs["before"] = before
        plan = session.predict_action(before.observation_id, "act", command, predictor=args.predictor)
        if isinstance(plan, PreparedAction):
            after = session.execute(plan, ObservationRequest("after", mode, args.view_arm), changes=changes)
            after_answer = read_public_package(schema, after.ao_bytes, after.attachments)
            outputs["transition"] = after
            if after.action_ticket is not None:
                session.action_feedback(after.action_ticket)
            submit_scored_view(session, before, before_answer, scores)
            submit_scored_view(session, after, after_answer, scores)
            outputs["next"] = session.observe(ObservationRequest("next", mode, args.view_arm), changes=changes)

    # Consume and persist public bytes after Blender resources have been released.
    answers = {}
    attachments = {}
    for name, result in outputs.items():
        answers[name] = read_public_package(schema, result.ao_bytes, result.attachments)
        attachments.update(result.attachments)
        (args.out / f"{name}.ao.json").write_bytes(result.ao_bytes)
    for key, png in attachments.items():
        (args.out / key).write_bytes(png)
    for name, payload in (("schema", schema), ("public-results", answers)):
        (args.out / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--view-layer", required=True)
    parser.add_argument("--object", action="append", metavar="ID=NAME", required=True)
    parser.add_argument("--generation", action="append", metavar="ID=NUMBER",
                        help="Explicit topology generations for all objects")
    parser.add_argument("--moving", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--reference-frame", type=int, required=True)
    parser.add_argument("--frame", type=int, required=True)
    parser.add_argument("--goal-distance-m", type=float, required=True)
    parser.add_argument("--goal-tolerance-m", type=float, default=0.0)
    parser.add_argument("--mode", choices=("NATURAL", "SECTION", "NONE"), required=True)
    parser.add_argument("--deployment", type=Path)
    parser.add_argument("--view-arm", choices=("F", "R", "L"), default="F")
    parser.add_argument("--predictor", choices=("NONE", "G", "L"), default="G")
    parser.add_argument("--view-scores", type=Path, help="Optional scored JSON keyed by observation ID")
    parser.add_argument("--out", type=Path, required=True)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--translate", type=float, nargs=3, metavar=("X", "Y", "Z"))
    command.add_argument("--shape-key", nargs=2, metavar=("KEY", "VALUE"))
    run(parser.parse_args(sys.argv[sys.argv.index("--") + 1:]))


if __name__ == "__main__":
    main()
