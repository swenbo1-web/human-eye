"""Analyse only explicitly supplied content-free request trace JSONL files.

No host session databases, prompts or existing blind-test outputs are opened.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from human_eye_plugin.telemetry import summarize_traces


def analyze_paths(paths):
    records, issues = [], []
    ignored_operational_records = 0
    wrapped_trace_records = 0
    for supplied in paths:
        path = Path(supplied).resolve()
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    if isinstance(item, dict) and item.get("event") == "request_trace":
                        records.append(item.get("trace"))
                        wrapped_trace_records += 1
                    elif isinstance(item, dict) and isinstance(item.get("event"), str):
                        ignored_operational_records += 1
                    else:
                        records.append(item)
                except (ValueError, TypeError):
                    issues.append({"file": path.name, "line": line_number,
                                   "issue": "invalid_json_record"})
    report = summarize_traces(records)
    report["input_files"] = [str(Path(path).resolve()) for path in paths]
    report["read_issues"] = issues
    report["ignored_operational_records"] = ignored_operational_records
    report["wrapped_trace_records"] = wrapped_trace_records
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Explicit trace JSONL files")
    parser.add_argument("--output", type=Path, help="Optional new report JSON path")
    args = parser.parse_args(argv)
    report = analyze_paths(args.paths)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output is not None:
        # Refuse accidental overwrite of a source log or historical report.
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
