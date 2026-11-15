"""Bounded data paths and JSON/byte identities, with no model dependency."""

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
DEPS = HERE.parent / "m6_shape_pretrain_001/private/deps"
sys.path.insert(0, str(DEPS))
sys.path.append("C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages")


def read(name):
    return json.loads((HERE / name).read_bytes())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf8", newline="\n")


def identity(path):
    path = Path(path)
    data = path.read_bytes()
    return dict(path=path.relative_to(HERE).as_posix() if path.is_relative_to(HERE) else str(path),
                bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
