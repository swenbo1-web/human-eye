"""Direct NPZ and persistent JSONL entry points for trusted local data."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from .engine import FastSession


def load_npz(path):
    """Archive keys: reference, triangles, and frame_<label> arrays."""
    with np.load(path) as archive:
        session = FastSession(archive["reference"], archive["triangles"])
        labels = []
        for key in archive.files:
            if key.startswith("frame_"):
                label = key[6:]
                session.set_frame(label, archive[key])
                labels.append(label)
    return session, labels


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def serve(instream=sys.stdin, outstream=sys.stdout):
    """One resident session. Commands fail directly; no retries or recovery ledger."""
    session = None
    labels = []
    for line in instream:
        command = json.loads(line)
        operation = command.pop("op")
        if operation == "load":
            session, labels = load_npz(command["path"])
            reply = {"loaded": labels}
        elif operation == "query":
            reply = session.query(command.pop("labels", labels), **command)
        elif operation == "update":
            vertices = (np.load(command["vertices_file"]) if "vertices_file" in command
                        else np.asarray(command["vertices"], dtype=np.float64))
            label = command["label"]
            reply = session.set_frame(label, vertices, changed_vertices=command.get("changed_vertices"))
            if label not in labels:
                labels.append(label)
        elif operation == "rows":
            reply = session.rows(command["label"], command["indices"])
        elif operation == "close":
            outstream.write(encode({"closed": True}) + "\n")
            outstream.flush()
            return
        else:
            raise KeyError(operation)
        outstream.write(encode(reply) + "\n")
        outstream.flush()


def demo_data():
    reference = np.array([[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.]])
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return dict(reference=reference, triangles=triangles, frame_rest=reference,
                frame_deformed=reference * np.array([1.5, .6, 1.]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    analyze = sub.add_parser("analyze", help="Load NPZ once and emit a compact task view")
    analyze.add_argument("input")
    analyze.add_argument("--labels", nargs="+")
    analyze.add_argument("--bounds", nargs=6, type=float, metavar="COORD")
    analyze.add_argument("--high", type=float, default=1.1)
    analyze.add_argument("--low", type=float, default=.9)
    analyze.add_argument("--witnesses", type=int, default=4)
    analyze.add_argument("--output")
    demo = sub.add_parser("demo", help="Two triangles, rest and anisotropic deformation")
    demo.add_argument("--write-input")
    sub.add_parser("serve", help="Persistent JSONL load/update/query/rows/close")
    args = parser.parse_args(argv)
    if args.operation == "serve":
        serve()
        return
    if args.operation == "demo":
        data = demo_data()
        if args.write_input:
            np.savez(args.write_input, **data)
        session = FastSession(data["reference"], data["triangles"])
        for label in ("rest", "deformed"):
            session.set_frame(label, data["frame_" + label])
        result = session.query(["rest", "deformed"])
    else:
        session, labels = load_npz(args.input)
        bounds = None if args.bounds is None else [args.bounds[:3], args.bounds[3:]]
        result = session.query(args.labels or labels, bounds=bounds, threshold_high=args.high,
                               threshold_low=args.low, max_witnesses=args.witnesses)
    payload = encode(result) + "\n"
    if getattr(args, "output", None):
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
