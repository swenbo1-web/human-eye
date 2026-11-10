"""Add the root-requested common budget prefix, preserving first assembly."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def save_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def main():
    public = ROOT / "input"
    old = (public / "PROMPT.txt").read_bytes()
    assert sha(old) == "94c2a0c4e7cf454a9b4f9a1b5f1f6706703c6e943b600ca7aaff068f0b683b61"
    manifest = ROOT / "scoring/INPUT_BINDING.json"
    old_binding = manifest.read_bytes()
    save_new(public / "history/PROMPT_before_budget_prefix.txt", old)
    save_new(ROOT / "scoring/history/INPUT_BINDING_before_budget_prefix.json", old_binding)
    rules = (public / "SESSION_RULES.txt").read_bytes()
    final = rules + b"\n" + old
    (public / "PROMPT.txt").write_bytes(final)
    data = json.loads(old_binding)
    data["inputs"].update(prompt_sha256=sha(final), prompt_bytes=len(final))
    data["shared_rules"] = {"path": "input/SESSION_RULES.txt", "sha256": sha(rules), "identical_N_P": True,
        "no_extra_numeric_accuracy_gate": True, "reason": "root requested explicit unchanged tool/session budget disclosure before freeze"}
    data["prompt_composition"] = ["input/SESSION_RULES.txt", "newline", *data["prompt_composition"]]
    data["initial_budgetless_assembly_preserved"] = {"path": "input/history/PROMPT_before_budget_prefix.txt", "sha256": sha(old)}
    manifest.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())
    assert (public / "PROMPT.txt").read_bytes() == final
    print(json.dumps(data["inputs"]))


if __name__ == "__main__":
    main()
