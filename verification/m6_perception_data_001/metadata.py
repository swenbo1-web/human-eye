"""Measure all selected undamaged meshes before the generation plan is frozen."""

from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import read, write
import numpy as np
from geometry import mesh_geometry


def main():
    started, cpu = time.perf_counter(), time.process_time()
    meshes = []
    for row in read("ACQUISITION.json")["selected"]:
        with np.load(HERE / row["array_path"]) as source:
            geometry = mesh_geometry(**{key: source[key] for key in source.files})
        meshes.append(dict(id=row["id"], **geometry["stats"]))
        print(row["id"], geometry["stats"], flush=True)
    write("SOURCE_GEOMETRY.json", dict(meshes=meshes, wall_s_before_write=time.perf_counter() - started,
                                       cpu_s_before_write=time.process_time() - cpu))


if __name__ == "__main__":
    main()
