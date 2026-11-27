"""Make scoped 049 copies of the audited 045 client and offline lifecycle audit."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parents[1] / "m6_r3_replacement_entry_045"
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT/g60_b02")


def pin(path):
    path = Path(path).resolve(strict=True)
    return dict(path=str(path), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def write(path, data):
    with path.open("xb") as stream:
        stream.write(data)
    return pin(path)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    refs = {}
    source = OLD / "g60_windows.py"
    refs["windows"] = dict(original=pin(source), copy=write(HERE / "g60_windows.py", source.read_bytes()),
                           change="byte-identical")
    source = OLD / "g60_client.py"
    text = source.read_text(encoding="utf-8")
    text = text.replace('assert name=="G60"', 'assert name in ("G60", "B02")')
    text = text.replace('ident["source_file_count"]==143', 'ident["source_file_count"]==self.install["source_file_count"]')
    refs["client"] = dict(original=pin(source), copy=write(HERE / "client.py", text.encode("utf-8")),
        changes=["Accept both fixed fixture labels in the open guard.",
                 "Verify negotiated source file count against the frozen arm manifest, including the final candidate."])
    source = OLD / "g60_verify.py"
    text = source.read_text(encoding="utf-8")
    tree = ast.parse(text)
    names = {"PARENT_CLOCK", "PROCESS_CLOCK", "OS_BRACKET_100NS", "DRIFT_TOLERANCE_NS", "IO_NAMES", "MAIN_ORDER",
             "need", "integer", "read", "pin", "union_length", "clipped_union", "event_map", "validate_lifecycle"}
    parts = []
    for node in tree.body:
        name = getattr(node, "name", None)
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        if name in names:
            parts.append(ast.get_source_segment(text, node))
    assert len(parts) == len(names)
    extracted = ('"""049 offline lifecycle proof; extracted from the frozen 045 verifier."""\n'
                 'from __future__ import annotations\nimport hashlib\nimport json\nfrom pathlib import Path\n\n' +
                 "\n\n\n".join(parts) + "\n")
    old = 'archive["files"] == len(actual) == (11 if business else 5)'
    new = 'archive["files"] == len(actual) == (5 + 2*len(record["rows"]) if business else 5)'
    assert extracted.count(old) == 1
    extracted = extracted.replace(old, new)
    ast.parse(extracted)
    refs["lifecycle"] = dict(original=pin(source), copy=write(HERE / "lifecycle.py", extracted.encode("utf-8")),
        extracted_definitions=sorted(names),
        change="Only business wire inventory becomes 5+2*actual frozen row count: G60=11, B02=9. All original lifecycle, ownership, clock and ordering checks retained.")
    record = dict(schema="m6-049-original-045-harness-custody-v1", status="prepared_no_process",
                  preparation_source=pin(__file__), copies=refs, Blender=0, product_processes=0, formal_timing=0)
    data = (json.dumps(record, indent=2) + "\n").encode()
    print(write(HERE / "SOURCE_CUSTODY.json", data))
    print(write(RAW / "SOURCE_CUSTODY.json", data))


if __name__ == "__main__":
    main()
