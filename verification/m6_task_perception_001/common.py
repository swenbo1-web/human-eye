"""I/O and measured scopes for the isolated task-perception experiment."""

import hashlib
import json
from pathlib import Path
import sys
import time
from contextlib import contextmanager

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = HERE.parent / "m6_perception_data_001"
DEPS = HERE.parent / "m6_shape_pretrain_001/private/deps"
sys.path.insert(0, str(DEPS))


def read(name):
    return json.loads((HERE / name).read_bytes())


def write(name, value):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def identity(path):
    path = Path(path)
    data = path.read_bytes()
    return dict(path=path.relative_to(HERE).as_posix() if path.is_relative_to(HERE) else str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


@contextmanager
def measure(timings, name):
    wall, cpu = time.perf_counter(), time.process_time()
    try:
        yield
    finally:
        row = timings.setdefault(name, dict(wall_s=0., cpu_s=0., calls=0))
        row["wall_s"] += time.perf_counter() - wall
        row["cpu_s"] += time.process_time() - cpu
        row["calls"] += 1
