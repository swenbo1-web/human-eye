"""Copy frozen public inputs and assemble the one common N/P text; no engine."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = Path("D:/hefe/verification/fixes/20261103_spatial_perception_qual002")
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    assert path.read_bytes() == raw


def main():
    manifest_raw = (OLD / "admin/INPUT_FREEZE.json").read_bytes()
    manifest = json.loads(manifest_raw)
    entries = {row["path"]: row for row in manifest["inputs"]}
    expected = {"scene.blend", "INITIAL.png", "INITIAL_VIEW.json", "CATALOG.json", "DIRECTIONS.txt", "TASK.txt", "ANSWER_SCHEMA.json"}
    assert set(entries) == expected
    public = ROOT / "input"
    originals = {}
    for name in sorted(entries):
        raw = (OLD / "shared" / name).read_bytes()
        assert sha(raw) == entries[name]["sha256"] and len(raw) == entries[name]["bytes"]
        put(public / "original" / name, raw)
        originals[name] = raw
    for name in ("scene.blend", "INITIAL.png", "INITIAL_VIEW.json", "CATALOG.json"):
        put(public / name, originals[name])
    task = (public / "TASK.txt").read_bytes()
    directions = (public / "DIRECTIONS.txt").read_bytes()
    prompt = (task + b"\n" + directions + "\n完整中性目录（原件全文）：\n".encode("utf8")
              + originals["CATALOG.json"] + "\n原始初图相机元数据（原件全文）：\n".encode("utf8")
              + originals["INITIAL_VIEW.json"])
    put(public / "PROMPT.txt", prompt)
    assert prompt.decode("utf8").encode("utf8") == prompt
    source = {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in originals.items()}
    result = {"schema": "M4-observation-public-input-binding-v1", "cycle_id": "M4-OBSERVATION-BASELINE-001",
        "source_shared": str(OLD / "shared"), "source_freeze_sha256": sha(manifest_raw),
        "originals": source, "copies_exact": True,
        "inputs": {"prompt": "input/PROMPT.txt", "prompt_sha256": sha(prompt), "prompt_bytes": len(prompt),
            "image": "input/INITIAL.png", "image_sha256": sha(originals["INITIAL.png"]), "image_bytes": len(originals["INITIAL.png"]),
            "scene": "input/scene.blend", "scene_sha256": sha(originals["scene.blend"])},
        "prompt_composition": ["input/TASK.txt", "newline", "input/DIRECTIONS.txt", "catalogue header",
                               "original CATALOG.json bytes", "camera header", "original INITIAL_VIEW.json bytes"],
        "N_P_text_identical": True, "initial_image_delivery": "pending_actual_consumer_receipt; path copy is not proof of model receipt",
        "new_assets": 0, "new_images": 0, "model_consumers": 0,
        "scope": "new natural-language delivery contract on unchanged historical spatial task; no old schema requirement is consumer input"}
    put(ROOT / "scoring/INPUT_BINDING.json", (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode())
    assert all((OLD / "shared" / name).read_bytes() == raw for name, raw in originals.items())
    print(json.dumps(result["inputs"]))


if __name__ == "__main__":
    main()
