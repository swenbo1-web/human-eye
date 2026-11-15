"""Shared isolated paths, immutable identities and measured costs."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PYTHON=HERE.parent/"m6_shape_train_001/private/venv/Scripts/python.exe"
BLENDER=Path("D:/Tools/blender5.2/blender.exe")
sys.path.insert(0,str(HERE.parent/"m6_shape_pretrain_001/private/deps"))


def read(path):
    return json.loads((HERE/path).read_bytes())


def write(path,value):
    target=HERE/path
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+".next")
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf8",newline="\n")
    temporary.replace(target)


def identity(path):
    path=Path(path).resolve()
    data=path.read_bytes()
    return dict(path=path.relative_to(HERE).as_posix() if path.is_relative_to(HERE) else str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


@contextmanager
def measure(timings,name):
    wall,cpu=time.perf_counter(),time.process_time()
    try:
        yield
    finally:
        row=timings.setdefault(name,dict(wall_s=0.,cpu_s=0.,calls=0))
        row["wall_s"]+=time.perf_counter()-wall
        row["cpu_s"]+=time.process_time()-cpu
        row["calls"]+=1
